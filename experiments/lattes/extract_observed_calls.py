#!/usr/bin/env python3
"""Extract observed tool / MCP call evidence from COPA query traces.

This script is designed for COPA baseline folders such as:

    baseline_001/
      answers.jsonl
      traces/queries/<runId>.json

It creates CSV files that can be read directly from a notebook:

    observed_tool_calls_by_run.csv      # one row per answer run
    observed_tool_calls_long.csv        # one row per observed call
    observed_tool_calls_summary.csv     # grouped summary by provider/model/strategy/format

The important detail is that remote MCP calls may not appear in
metricsSummary.toolCalls. For the remote `mcp` strategy, this script inspects
provider-native MCP evidence recorded under trace.nativeMcp and, as a fallback,
aiTrace event metadata.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


RUN_COLUMNS = [
    "experimentId",
    "runId",
    "provider",
    "modelId",
    "model",
    "strategy",
    "format",
    "questionId",
    "instanceId",
    "status",
    "traceRef",
    "traceExists",
    "metricsToolCalls",
    "metricsMcpToolCalls",
    "metricsFunctionCalls",
    "metricsModelCalls",
    "metricsSteps",
    "observedCallCount",
    "observedCallCoverage",
    "observedCallSource",
    "observedCallNames",
    "observedCallNamesNormalized",
    "nativeMcpCallCount",
    "nativeMcpVisibleToolCallCount",
    "nativeMcpApprovalRequestCount",
    "rawResponseHasMcpEvidence",
]

CALL_COLUMNS = [
    "experimentId",
    "runId",
    "provider",
    "modelId",
    "model",
    "strategy",
    "format",
    "questionId",
    "instanceId",
    "callIndex",
    "source",
    "name",
    "normalizedName",
    "argumentsJson",
    "status",
    "isError",
    "durationMs",
    "serverLabel",
    "outputBytes",
]

SUMMARY_COLUMNS = [
    "provider",
    "modelId",
    "model",
    "strategy",
    "format",
    "runs",
    "runsWithObservedCalls",
    "observedCallCoveragePct",
    "totalObservedCalls",
    "meanObservedCalls",
    "meanMetricsToolCalls",
    "meanMetricsMcpToolCalls",
    "meanMetricsFunctionCalls",
]


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def as_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_tool_name(name: str | None) -> str:
    value = (name or "").strip()
    # Gemini native MCP traces often expose names with the server prefix.
    for prefix in ("copa_lattes_", "copa-lattes-", "copa.lattes."):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def safe_json_dumps(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        # OpenAI native MCP stores arguments as a JSON string in some traces.
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def output_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    try:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    except TypeError:
        return len(str(value).encode("utf-8"))


def trace_payload(trace_doc: dict[str, Any] | None) -> dict[str, Any]:
    if not trace_doc:
        return {}
    trace = trace_doc.get("trace")
    return trace if isinstance(trace, dict) else {}


def extract_benchmark_tool_calls(trace: dict[str, Any]) -> list[dict[str, Any]]:
    calls = trace.get("toolCalls")
    if not isinstance(calls, list):
        return []
    rows: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        rows.append(
            {
                "source": "trace.toolCalls",
                "name": call.get("name"),
                "arguments": call.get("arguments"),
                "status": "error" if call.get("isError") else "completed",
                "isError": bool(call.get("isError")),
                "durationMs": call.get("durationMs"),
                "serverLabel": "",
                "output": call.get("result"),
            }
        )
    return rows


def native_from_events(trace: dict[str, Any]) -> dict[str, Any]:
    events = trace.get("aiTrace", {}).get("events", [])
    if not isinstance(events, list):
        return {}
    for event in events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            continue
        native = metadata.get("native_mcp")
        if isinstance(native, dict):
            return native
    return {}


def extract_native_mcp_calls(trace: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], str]:
    native = trace.get("nativeMcp")
    source_prefix = "trace.nativeMcp"
    if not isinstance(native, dict) or not native:
        native = native_from_events(trace)
        source_prefix = "aiTrace.events.metadata.native_mcp"
    if not isinstance(native, dict) or not native:
        return [], {"callCount": 0, "visibleToolCallCount": 0, "approvalRequestCount": 0}, "none"

    call_count = as_int(native.get("callCount"))
    visible_count = as_int(native.get("visibleToolCallCount"))
    approval_count = as_int(native.get("approvalRequestCount"))

    rows: list[dict[str, Any]] = []

    # OpenAI native MCP format.
    calls = native.get("calls")
    if isinstance(calls, list):
        for call in calls:
            if not isinstance(call, dict):
                continue
            rows.append(
                {
                    "source": f"{source_prefix}.calls",
                    "name": call.get("name"),
                    "arguments": call.get("arguments"),
                    "status": call.get("status") or ("error" if call.get("error") else "completed"),
                    "isError": bool(call.get("error")),
                    "durationMs": call.get("durationMs"),
                    "serverLabel": call.get("server_label") or call.get("serverLabel") or "",
                    "output": call.get("output"),
                }
            )

    # Gemini native MCP format.
    visible_calls = native.get("visibleToolCalls")
    if isinstance(visible_calls, list):
        for call in visible_calls:
            if not isinstance(call, dict):
                continue
            rows.append(
                {
                    "source": f"{source_prefix}.visibleToolCalls",
                    "name": call.get("name"),
                    "arguments": call.get("arguments") or call.get("args"),
                    "status": call.get("status") or "observed",
                    "isError": bool(call.get("error")),
                    "durationMs": call.get("durationMs"),
                    "serverLabel": call.get("server_label") or call.get("serverLabel") or "",
                    "output": call.get("output"),
                }
            )

    # Some providers expose only the aggregate count. Keep the count even if the
    # concrete call list is missing, but do not invent per-call rows.
    counts = {
        "callCount": call_count or len([r for r in rows if r["source"].endswith(".calls")]),
        "visibleToolCallCount": visible_count or len([r for r in rows if r["source"].endswith(".visibleToolCalls")]),
        "approvalRequestCount": approval_count,
    }
    if rows:
        return rows, counts, rows[0]["source"].rsplit(".", 1)[0]
    if call_count or visible_count:
        return [], counts, source_prefix
    return [], counts, "none"


def raw_response_has_mcp_evidence(trace: dict[str, Any]) -> bool:
    raw = trace.get("rawResponse")
    if raw is None:
        return False

    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            t = value.get("type")
            if isinstance(t, str) and ("mcp" in t.lower() or t in {"mcp_call", "mcp_list_tools"}):
                return True
            if any(k in value for k in ("server_label", "serverLabel", "mcp", "native_mcp")):
                return True
            return any(walk(v) for v in value.values())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        if isinstance(value, str):
            s = value.lower()
            return "mcp_call" in s or "server_label" in s or "native_mcp" in s
        return False

    return walk(raw)


def observed_calls_for_run(answer: dict[str, Any], trace: dict[str, Any], *, scan_raw_response: bool = False) -> tuple[list[dict[str, Any]], dict[str, int], str, bool]:
    strategy = str(answer.get("strategy") or "")
    metrics = answer.get("metricsSummary") if isinstance(answer.get("metricsSummary"), dict) else {}

    if strategy == "inline":
        return [], {"callCount": 0, "visibleToolCallCount": 0, "approvalRequestCount": 0}, "inline-none", (raw_response_has_mcp_evidence(trace) if scan_raw_response else False)

    if strategy in {"local_function", "local_mcp"}:
        rows = extract_benchmark_tool_calls(trace)
        if rows:
            return rows, {"callCount": 0, "visibleToolCallCount": 0, "approvalRequestCount": 0}, "trace.toolCalls", (raw_response_has_mcp_evidence(trace) if scan_raw_response else False)
        # Fallback: only aggregate metric available.
        n = as_int(metrics.get("toolCalls"))
        rows = [
            {
                "source": "metricsSummary.toolCalls",
                "name": "",
                "arguments": None,
                "status": "observed-count-only",
                "isError": False,
                "durationMs": None,
                "serverLabel": "",
                "output": None,
            }
            for _ in range(n)
        ]
        return rows, {"callCount": 0, "visibleToolCallCount": 0, "approvalRequestCount": 0}, "metricsSummary.toolCalls", (raw_response_has_mcp_evidence(trace) if scan_raw_response else False)

    if strategy == "mcp":
        rows, counts, source = extract_native_mcp_calls(trace)
        if rows:
            return rows, counts, source, (raw_response_has_mcp_evidence(trace) if scan_raw_response else False)
        # Fallback for providers that expose only count fields.
        n = max(counts.get("callCount", 0), counts.get("visibleToolCallCount", 0))
        rows = [
            {
                "source": source,
                "name": "",
                "arguments": None,
                "status": "observed-count-only",
                "isError": False,
                "durationMs": None,
                "serverLabel": "",
                "output": None,
            }
            for _ in range(n)
        ]
        return rows, counts, source, (raw_response_has_mcp_evidence(trace) if scan_raw_response else False)

    return [], {"callCount": 0, "visibleToolCallCount": 0, "approvalRequestCount": 0}, "none", (raw_response_has_mcp_evidence(trace) if scan_raw_response else False)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})


def build_summary(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in run_rows:
        key = (
            str(row.get("provider") or ""),
            str(row.get("modelId") or ""),
            str(row.get("model") or ""),
            str(row.get("strategy") or ""),
            str(row.get("format") or ""),
        )
        groups[key].append(row)

    summary: list[dict[str, Any]] = []
    for (provider, model_id, model, strategy, fmt), rows in sorted(groups.items()):
        runs = len(rows)
        observed = [as_int(r.get("observedCallCount")) for r in rows]
        metrics_tool = [as_int(r.get("metricsToolCalls")) for r in rows]
        metrics_mcp = [as_int(r.get("metricsMcpToolCalls")) for r in rows]
        metrics_fn = [as_int(r.get("metricsFunctionCalls")) for r in rows]
        with_calls = sum(1 for n in observed if n > 0)
        summary.append(
            {
                "provider": provider,
                "modelId": model_id,
                "model": model,
                "strategy": strategy,
                "format": fmt,
                "runs": runs,
                "runsWithObservedCalls": with_calls,
                "observedCallCoveragePct": round((with_calls / runs * 100) if runs else 0, 2),
                "totalObservedCalls": sum(observed),
                "meanObservedCalls": round(mean(observed), 4) if observed else 0,
                "meanMetricsToolCalls": round(mean(metrics_tool), 4) if metrics_tool else 0,
                "meanMetricsMcpToolCalls": round(mean(metrics_mcp), 4) if metrics_mcp else 0,
                "meanMetricsFunctionCalls": round(mean(metrics_fn), 4) if metrics_fn else 0,
            }
        )
    return summary


def extract(experiment_dir: Path, output_dir: Path, *, scan_raw_response: bool = False) -> tuple[Path, Path, Path]:
    answers_path = experiment_dir / "answers.jsonl"
    if not answers_path.exists():
        raise FileNotFoundError(f"answers.jsonl not found: {answers_path}")

    run_rows: list[dict[str, Any]] = []
    call_rows: list[dict[str, Any]] = []

    for answer in read_jsonl(answers_path):
        trace_ref = str(answer.get("traceRef") or "")
        trace_path = experiment_dir / trace_ref if trace_ref else Path("")
        trace_doc = load_json(trace_path) if trace_ref else None
        trace = trace_payload(trace_doc)
        metrics = answer.get("metricsSummary") if isinstance(answer.get("metricsSummary"), dict) else {}
        calls, native_counts, source, raw_has_mcp = observed_calls_for_run(answer, trace, scan_raw_response=scan_raw_response)

        names = [str(c.get("name") or "") for c in calls if c.get("name")]
        normalized_names = [normalize_tool_name(name) for name in names]

        model = answer.get("model") or answer.get("modelName") or answer.get("metadata", {}).get("modelName") or ""
        base = {
            "experimentId": answer.get("experimentId"),
            "runId": answer.get("runId"),
            "provider": answer.get("provider"),
            "modelId": answer.get("modelId"),
            "model": model,
            "strategy": answer.get("strategy"),
            "format": answer.get("format"),
            "questionId": answer.get("questionId"),
            "instanceId": answer.get("instanceId"),
        }

        run_rows.append(
            {
                **base,
                "status": answer.get("status"),
                "traceRef": trace_ref,
                "traceExists": bool(trace_doc),
                "metricsToolCalls": as_int(metrics.get("toolCalls")),
                "metricsMcpToolCalls": as_int(metrics.get("mcpToolCalls")),
                "metricsFunctionCalls": as_int(metrics.get("functionCalls")),
                "metricsModelCalls": as_int(metrics.get("modelCalls")),
                "metricsSteps": as_int(metrics.get("steps")),
                "observedCallCount": len(calls),
                "observedCallCoverage": int(len(calls) > 0),
                "observedCallSource": source,
                "observedCallNames": ";".join(names),
                "observedCallNamesNormalized": ";".join(normalized_names),
                "nativeMcpCallCount": native_counts.get("callCount", 0),
                "nativeMcpVisibleToolCallCount": native_counts.get("visibleToolCallCount", 0),
                "nativeMcpApprovalRequestCount": native_counts.get("approvalRequestCount", 0),
                "rawResponseHasMcpEvidence": int(raw_has_mcp),
            }
        )

        for idx, call in enumerate(calls, start=1):
            name = str(call.get("name") or "")
            call_rows.append(
                {
                    **base,
                    "callIndex": idx,
                    "source": call.get("source"),
                    "name": name,
                    "normalizedName": normalize_tool_name(name),
                    "argumentsJson": safe_json_dumps(call.get("arguments")),
                    "status": call.get("status"),
                    "isError": int(bool(call.get("isError"))),
                    "durationMs": call.get("durationMs") if call.get("durationMs") is not None else "",
                    "serverLabel": call.get("serverLabel") or "",
                    "outputBytes": output_size(call.get("output")),
                }
            )

    by_run_path = output_dir / "observed_tool_calls_by_run.csv"
    long_path = output_dir / "observed_tool_calls_long.csv"
    summary_path = output_dir / "observed_tool_calls_summary.csv"

    write_csv(by_run_path, run_rows, RUN_COLUMNS)
    write_csv(long_path, call_rows, CALL_COLUMNS)
    write_csv(summary_path, build_summary(run_rows), SUMMARY_COLUMNS)
    return by_run_path, long_path, summary_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract observed COPA tool/MCP calls from query traces.")
    parser.add_argument("experiment_dir", type=Path, help="Experiment output directory containing answers.jsonl")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where CSV files will be written. Defaults to experiment_dir.",
    )
    parser.add_argument(
        "--scan-raw-response",
        action="store_true",
        help="Also recursively scan rawResponse for MCP evidence. This is slower and usually unnecessary when trace.nativeMcp is present.",
    )
    args = parser.parse_args()

    experiment_dir = args.experiment_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else experiment_dir
    paths = extract(experiment_dir, output_dir, scan_raw_response=args.scan_raw_response)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
