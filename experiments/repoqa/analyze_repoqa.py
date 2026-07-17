#!/usr/bin/env python3
"""Analyze preserved CTXBench RepoQA outputs without provider calls.

The script joins responses and deterministic RepoQA evaluations by trialId,
optionally applies an explicit paper-selection manifest, and writes the tables
used by the SBES 2026 LLMContextBench tool-paper analysis.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

CONFIG_ORDER = ["I-Code", "I-JSON", "Func.", "L-MCP"]
INSTANCE_RE = re.compile(r"^(?P<lang>[A-Za-z]+)_.+?_ctx(?P<size>\d+)k$")
LANGUAGES = {
    "py": "python",
    "python": "python",
    "java": "java",
    "ts": "typescript",
    "typescript": "typescript",
    "rs": "rust",
    "rust": "rust",
}


class ArtifactError(RuntimeError):
    pass


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        raise ArtifactError(f"Missing required file: {path}")
    with path.open(encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ArtifactError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ArtifactError(f"Expected object in {path}:{line_number}")
            yield value


def nested(payload: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "pass", "passed"}:
            return True
        if normalized in {"false", "no", "0", "fail", "failed"}:
            return False
    return None


def configuration(strategy: Any, context_format: Any) -> str:
    strategy = str(strategy or "").lower()
    context_format = str(context_format or "").lower()
    if strategy == "inline" and context_format in {"code", "text", "txt"}:
        return "I-Code"
    if strategy == "inline" and context_format == "json":
        return "I-JSON"
    if strategy == "local_function":
        return "Func."
    if strategy == "local_mcp":
        return "L-MCP"
    return f"{strategy or 'unknown'}:{context_format or 'unknown'}"


def instance_metadata(instance_id: str, evaluation: Mapping[str, Any]) -> tuple[str, int | None]:
    repoqa = nested(evaluation, "details", "repoqa", default={})
    reported = str(nested(repoqa, "language", default="") or "").lower()
    match = INSTANCE_RE.match(instance_id)
    prefix = match.group("lang").lower() if match else ""
    size = int(match.group("size")) if match else None
    return LANGUAGES.get(reported, LANGUAGES.get(prefix, reported or prefix or "unknown")), size


def call_count(response: Mapping[str, Any]) -> float:
    if str(response.get("strategy") or "") == "inline":
        return 0.0
    metrics = response.get("metricsSummary")
    if not isinstance(metrics, Mapping):
        return 0.0
    canonical = number(metrics.get("toolCalls"))
    if not math.isnan(canonical):
        return canonical
    candidates = [number(metrics.get("functionCalls")), number(metrics.get("mcpToolCalls"))]
    return max([item for item in candidates if not math.isnan(item)], default=0.0)


def response_path(experiment_dir: Path) -> Path:
    for name in ("responses.jsonl", "answers.jsonl"):
        candidate = experiment_dir / name
        if candidate.is_file():
            return candidate
    raise ArtifactError(f"No responses.jsonl or answers.jsonl in {experiment_dir}")


def load_trials(experiment_dir: Path, *, strict: bool = True) -> pd.DataFrame:
    evaluations: dict[str, dict[str, Any]] = {}
    for evaluation in read_jsonl(experiment_dir / "evals.jsonl"):
        trial_id = str(evaluation.get("trialId") or evaluation.get("runId") or "")
        if not trial_id:
            raise ArtifactError("Evaluation without trialId/runId")
        if trial_id in evaluations:
            raise ArtifactError(f"Duplicate evaluation: {trial_id}")
        evaluations[trial_id] = evaluation

    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for response in read_jsonl(response_path(experiment_dir)):
        trial_id = str(response.get("trialId") or response.get("runId") or "")
        if not trial_id:
            raise ArtifactError("Response without trialId/runId")
        if trial_id in seen:
            raise ArtifactError(f"Duplicate response: {trial_id}")
        seen.add(trial_id)
        evaluation = evaluations.get(trial_id)
        if evaluation is None:
            missing.append(trial_id)
            continue

        instance_id = str(response.get("instanceId") or evaluation.get("instanceId") or "")
        language, context_size = instance_metadata(instance_id, evaluation)
        repoqa = nested(evaluation, "details", "repoqa", default={})
        hit = boolean(nested(repoqa, "isBestMatch"))
        passed = boolean(nested(repoqa, "passed"))
        if passed is None:
            passed = boolean(nested(evaluation, "outcome", "passed"))

        usage = response.get("usage") if isinstance(response.get("usage"), Mapping) else {}
        metrics = response.get("metricsSummary") if isinstance(response.get("metricsSummary"), Mapping) else {}
        timing = response.get("timing") if isinstance(response.get("timing"), Mapping) else {}
        tokens = number(usage.get("totalTokens"))
        if math.isnan(tokens):
            tokens = number(metrics.get("totalTokens"))
        duration_ms = number(timing.get("durationMs"))
        if math.isnan(duration_ms):
            duration_ms = number(metrics.get("totalDurationMs"))
        strategy = str(response.get("strategy") or evaluation.get("strategy") or "")
        context_format = str(response.get("format") or nested(response, "metadata", "format", default="") or "")

        rows.append({
            "trial_id": trial_id,
            "experiment_id": response.get("experimentId") or evaluation.get("experimentId"),
            "instance_id": instance_id,
            "task_id": response.get("taskId") or evaluation.get("taskId"),
            "model_id": response.get("modelId") or nested(response, "metadata", "modelId"),
            "model": response.get("model") or nested(response, "metadata", "modelName"),
            "provider": response.get("provider") or nested(response, "metadata", "provider"),
            "strategy": strategy,
            "format": context_format,
            "configuration": configuration(strategy, context_format),
            "language": language,
            "context_size_k": context_size,
            "repository": nested(repoqa, "repo"),
            "target": nested(repoqa, "target"),
            "best_target": nested(repoqa, "bestTarget"),
            "threshold": number(nested(repoqa, "threshold")),
            "hit": hit,
            "passed": passed,
            "similarity": number(nested(repoqa, "bestSimilarScore")),
            "total_tokens": tokens,
            "duration_sec": duration_ms / 1000.0 if not math.isnan(duration_ms) else math.nan,
            "calls": call_count(response),
            "response_status": response.get("status"),
            "evaluation_status": evaluation.get("status"),
            "trace_ref": response.get("traceRef"),
        })

    if strict and missing:
        raise ArtifactError(f"{len(missing)} responses have no evaluation; first: {', '.join(missing[:5])}")
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ArtifactError("No joined RepoQA trials were loaded")
    for field in ("hit", "passed", "similarity", "total_tokens", "duration_sec"):
        if frame[field].isna().any() and strict:
            raise ArtifactError(f"{int(frame[field].isna().sum())} rows have missing {field}")
    return frame


def selection_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ArtifactError("Selection filter values must be arrays")
    return {str(item) for item in value}


def apply_selection(frame: pd.DataFrame, path: Path | None) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    if path is None:
        return frame.copy(), None
    if not path.is_file():
        raise ArtifactError(f"Selection file not found: {path}")
    selection = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(selection, dict):
        raise ArtifactError("Selection must be a JSON object")
    filters = selection.get("filters") or {}
    if not isinstance(filters, dict):
        raise ArtifactError("selection.filters must be an object")

    selected = frame.copy()
    mapping = {
        "trialIds": "trial_id", "instanceIds": "instance_id", "modelIds": "model_id",
        "models": "model", "providers": "provider", "strategies": "strategy",
        "formats": "format", "configurations": "configuration", "languages": "language",
    }
    for key, column in mapping.items():
        values = selection_values(filters.get(key))
        if values:
            selected = selected[selected[column].astype(str).isin(values)]
    if filters.get("contextSizesK"):
        sizes = {int(item) for item in filters["contextSizesK"]}
        selected = selected[selected["context_size_k"].isin(sizes)]
    excluded = selection_values(selection.get("excludeTrialIds"))
    if excluded:
        selected = selected[~selected["trial_id"].astype(str).isin(excluded)]
    if selected.empty:
        raise ArtifactError("Selection removed every trial")

    expected = selection.get("expectedPerConfiguration")
    if expected is not None:
        counts = selected.groupby("configuration").size().to_dict()
        unexpected = {key: value for key, value in counts.items() if value != int(expected)}
        if unexpected:
            rendered = ", ".join(f"{key}={value}" for key, value in sorted(unexpected.items()))
            raise ArtifactError(f"Unexpected trials per configuration: {rendered}")
    return selected.reset_index(drop=True), selection


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for config, group in frame.groupby("configuration", sort=False):
        n = len(group)
        passed_count = int(group["passed"].astype(bool).sum())
        token_total = float(group["total_tokens"].sum())
        records.append({
            "Config": config,
            "N": int(n),
            "Hit": float(group["hit"].astype(float).mean() * 100),
            "Pass": float(group["passed"].astype(float).mean() * 100),
            "Sim.": float(group["similarity"].mean()),
            "Tok./T": token_total / n,
            "Tok./P": token_total / passed_count if passed_count else math.nan,
            "Sec.": float(group["duration_sec"].median()),
            "Calls": float(group["calls"].mean()),
            "Passed": passed_count,
        })
    result = pd.DataFrame(records)
    order = {name: index for index, name in enumerate(CONFIG_ORDER)}
    result["_order"] = result["Config"].map(order).fillna(len(order))
    return result.sort_values(["_order", "Config"]).drop(columns="_order").reset_index(drop=True)


def summarize_dimension(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    result = frame.groupby([dimension, "configuration"], dropna=False).agg(
        N=("trial_id", "size"), Hit=("hit", "mean"), Pass=("passed", "mean"),
        Similarity=("similarity", "mean"), MeanTokens=("total_tokens", "mean"),
        MedianSec=("duration_sec", "median"), MeanCalls=("calls", "mean"),
    ).reset_index()
    result["Hit"] *= 100
    result["Pass"] *= 100
    return result


def format_k(value: float) -> str:
    return "--" if math.isnan(value) else f"{value / 1000:.1f}k"


def write_latex(summary: pd.DataFrame, path: Path) -> None:
    lines = [
        r"\begin{tabular}{lrrrrrrrr}", r"\toprule",
        r"Config. & N & Hit & Pass & Sim. & Tok./T & Tok./P & Sec. & Calls \\",
        r"\midrule",
    ]
    for row in summary.to_dict(orient="records"):
        lines.append(
            f"{row['Config']} & {int(row['N'])} & {row['Hit']:.1f} & {row['Pass']:.1f} & "
            f"{row['Sim.']:.2f} & {format_k(float(row['Tok./T']))} & "
            f"{format_k(float(row['Tok./P']))} & {row['Sec.']:.2f} & {row['Calls']:.2f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def expected_number(value: Any) -> float:
    text = str(value).strip()
    if not text or text == "--":
        return math.nan
    multiplier = 1000 if text.lower().endswith("k") else 1
    return float(text[:-1] if multiplier == 1000 else text) * multiplier


def verify(summary: pd.DataFrame, expected_path: Path) -> list[str]:
    expected = pd.read_csv(expected_path)
    actual = {row["Config"]: row for row in summary.to_dict(orient="records")}
    tolerances = {"Hit": .15, "Pass": .15, "Sim.": .015, "Tok./T": 150, "Tok./P": 150, "Sec.": .11, "Calls": .025}
    errors: list[str] = []
    for row in expected.to_dict(orient="records"):
        config = str(row["Config"])
        found = actual.get(config)
        if found is None:
            errors.append(f"Missing configuration {config}")
            continue
        if int(found["N"]) != int(row["N"]):
            errors.append(f"{config} N: expected {int(row['N'])}, got {int(found['N'])}")
        for metric, tolerance in tolerances.items():
            expected_value = expected_number(row[metric])
            actual_value = float(found[metric])
            if math.isnan(actual_value) or abs(actual_value - expected_value) > tolerance:
                errors.append(f"{config} {metric}: expected {expected_value:g}, got {actual_value:g}")
    return errors


def write_outputs(frame: pd.DataFrame, output_dir: Path, selection: dict[str, Any] | None, source: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(frame)
    frame.sort_values(["configuration", "language", "context_size_k", "model_id", "instance_id"]).to_csv(output_dir / "repoqa_trials.csv", index=False)
    summary.to_csv(output_dir / "repoqa_summary_by_configuration.csv", index=False)
    columns = ["Config", "N", "Hit", "Pass", "Sim.", "Tok./T", "Tok./P", "Sec.", "Calls"]
    summary[columns].to_csv(output_dir / "tool-paper-table-3b.csv", index=False)
    write_latex(summary, output_dir / "tool-paper-table-3b.tex")
    for dimension, name in (("model", "repoqa_summary_by_model.csv"), ("language", "repoqa_summary_by_language.csv"), ("context_size_k", "repoqa_summary_by_context_size.csv")):
        summarize_dimension(frame, dimension).to_csv(output_dir / name, index=False)
    failures = frame[(~frame["passed"].astype(bool)) | (~frame["hit"].astype(bool))]
    failures.to_csv(output_dir / "repoqa_failures.csv", index=False)
    manifest = {
        "sourceDirectory": str(source), "selection": selection, "joinedTrials": int(len(frame)),
        "configurations": {str(k): int(v) for k, v in frame.groupby("configuration").size().items()},
        "models": sorted(str(v) for v in frame["model"].dropna().unique()),
        "languages": sorted(str(v) for v in frame["language"].dropna().unique()),
        "contextSizesK": sorted(int(v) for v in frame["context_size_k"].dropna().unique()),
    }
    (output_dir / "repoqa_analysis_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_dir", type=Path, nargs="?", default=Path("experiments/repoqa/baseline-01"))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--selection", type=Path, default=None)
    parser.add_argument("--expected", type=Path, default=None)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--allow-missing-evaluations", action="store_true")
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    output_dir = (args.output_dir or experiment_dir / "derived" / "analysis").resolve()
    try:
        frame = load_trials(experiment_dir, strict=not args.allow_missing_evaluations)
        frame, selection = apply_selection(frame, args.selection.resolve() if args.selection else None)
        summary = write_outputs(frame, output_dir, selection, experiment_dir)
    except (ArtifactError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(summary[["Config", "N", "Hit", "Pass", "Sim.", "Tok./T", "Tok./P", "Sec.", "Calls"]].to_string(index=False))
    print(f"Wrote RepoQA analysis to {output_dir}")
    if args.expected:
        errors = verify(summary, args.expected.resolve())
        if errors:
            print("Paper-value verification failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1 if args.verify else 0
        print("Paper-value verification passed.")
    elif args.verify:
        print("ERROR: --verify requires --expected", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
