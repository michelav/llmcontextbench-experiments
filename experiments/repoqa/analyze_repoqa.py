#!/usr/bin/env python3
"""Analyze preserved CTXBench RepoQA outputs without provider calls.

The module joins responses and deterministic RepoQA evaluations by trial ID and
provides shared normalization, optional diagnostic filtering, and summarization
helpers. It does not validate results against aggregate values copied from the
article.
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
REQUIRED_ANALYSIS_FIELDS = (
    "hit",
    "passed",
    "similarity",
    "total_tokens",
    "duration_sec",
    "calls",
)


class ArtifactError(RuntimeError):
    """Raised when preserved experiment artifacts are structurally inconsistent."""


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
    strategy_text = str(strategy or "").lower()
    format_text = str(context_format or "").lower()
    if strategy_text == "inline" and format_text in {"code", "text", "txt"}:
        return "I-Code"
    if strategy_text == "inline" and format_text == "json":
        return "I-JSON"
    if strategy_text == "local_function":
        return "Func."
    if strategy_text == "local_mcp":
        return "L-MCP"
    return f"{strategy_text or 'unknown'}:{format_text or 'unknown'}"


def instance_metadata(instance_id: str, evaluation: Mapping[str, Any]) -> tuple[str, int | None]:
    repoqa = nested(evaluation, "details", "repoqa", default={})
    reported = str(nested(repoqa, "language", default="") or "").lower()
    match = INSTANCE_RE.match(instance_id)
    prefix = match.group("lang").lower() if match else ""
    size = int(match.group("size")) if match else None
    language = LANGUAGES.get(reported, LANGUAGES.get(prefix, reported or prefix or "unknown"))
    return language, size


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


def missing_reasons(row: Mapping[str, Any], evaluation_present: bool) -> list[str]:
    reasons: list[str] = []
    if not evaluation_present:
        reasons.append("missing_evaluation")
    for field in REQUIRED_ANALYSIS_FIELDS:
        value = row.get(field)
        if value is None or pd.isna(value):
            reasons.append(f"missing_{field}")
    return reasons


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
    seen: set[str] = set()
    for response in read_jsonl(response_path(experiment_dir)):
        trial_id = str(response.get("trialId") or response.get("runId") or "")
        if not trial_id:
            raise ArtifactError("Response without trialId/runId")
        if trial_id in seen:
            raise ArtifactError(f"Duplicate response: {trial_id}")
        seen.add(trial_id)

        evaluation_present = trial_id in evaluations
        evaluation = evaluations.get(trial_id, {})
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
        context_format = str(
            response.get("format") or nested(response, "metadata", "format", default="") or ""
        )

        row: dict[str, Any] = {
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
            "evaluation_status": evaluation.get("status") if evaluation_present else None,
            "evaluation_present": evaluation_present,
            "trace_ref": response.get("traceRef"),
        }
        reasons = missing_reasons(row, evaluation_present)
        row["analysis_complete"] = not reasons
        row["incomplete_reasons"] = ";".join(reasons)
        rows.append(row)

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ArtifactError("No RepoQA responses were loaded")

    orphan_evaluations = sorted(set(evaluations).difference(seen))
    if strict:
        incomplete = frame.loc[~frame["analysis_complete"]]
        if not incomplete.empty:
            examples = ", ".join(incomplete["trial_id"].astype(str).head(5))
            raise ArtifactError(
                f"{len(incomplete)} rows have incomplete analysis metrics; first: {examples}"
            )
        if orphan_evaluations:
            raise ArtifactError(
                f"{len(orphan_evaluations)} evaluations have no response; first: "
                + ", ".join(orphan_evaluations[:5])
            )
    return frame


def selection_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ArtifactError("Selection filter values must be arrays")
    return {str(item) for item in value}


def apply_selection(
    frame: pd.DataFrame, path: Path | None
) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    """Apply optional diagnostic filters from a JSON file.

    Filtering is intended for exploratory analysis and figure generation; it is
    not a paper-value validation mechanism.
    """

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
        "trialIds": "trial_id",
        "instanceIds": "instance_id",
        "modelIds": "model_id",
        "models": "model",
        "providers": "provider",
        "strategies": "strategy",
        "formats": "format",
        "configurations": "configuration",
        "languages": "language",
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
    return selected.reset_index(drop=True), selection


def complete_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if "analysis_complete" in frame.columns:
        mask = frame["analysis_complete"].fillna(False).astype(bool)
    else:
        mask = ~frame[list(REQUIRED_ANALYSIS_FIELDS)].isna().any(axis=1)
    return frame.loc[mask].copy()


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for config, group in frame.groupby("configuration", sort=False):
        complete = complete_rows(group)
        complete_n = len(complete)
        passed_count = int(complete["passed"].eq(True).sum())
        token_total = float(complete["total_tokens"].sum())
        records.append(
            {
                "Config": config,
                "N": int(len(group)),
                "CompleteN": int(complete_n),
                "Hit": float(complete["hit"].astype(float).mean() * 100) if complete_n else math.nan,
                "Pass": float(complete["passed"].astype(float).mean() * 100) if complete_n else math.nan,
                "Sim.": float(complete["similarity"].mean()) if complete_n else math.nan,
                "Tok./T": token_total / complete_n if complete_n else math.nan,
                "Tok./P": token_total / passed_count if passed_count else math.nan,
                "Sec.": float(complete["duration_sec"].median()) if complete_n else math.nan,
                "Calls": float(complete["calls"].mean()) if complete_n else math.nan,
                "Passed": passed_count,
            }
        )
    result = pd.DataFrame(records)
    order = {name: index for index, name in enumerate(CONFIG_ORDER)}
    result["_order"] = result["Config"].map(order).fillna(len(order))
    return result.sort_values(["_order", "Config"]).drop(columns="_order").reset_index(drop=True)


def summarize_dimension(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for keys, group in frame.groupby([dimension, "configuration"], dropna=False, sort=False):
        dimension_value, config = keys
        complete = complete_rows(group)
        complete_n = len(complete)
        records.append(
            {
                dimension: dimension_value,
                "configuration": config,
                "N": int(len(group)),
                "CompleteN": int(complete_n),
                "Hit": float(complete["hit"].astype(float).mean() * 100) if complete_n else math.nan,
                "Pass": float(complete["passed"].astype(float).mean() * 100) if complete_n else math.nan,
                "Similarity": float(complete["similarity"].mean()) if complete_n else math.nan,
                "MeanTokens": float(complete["total_tokens"].mean()) if complete_n else math.nan,
                "MedianSec": float(complete["duration_sec"].median()) if complete_n else math.nan,
                "MeanCalls": float(complete["calls"].mean()) if complete_n else math.nan,
            }
        )
    return pd.DataFrame(records)


def write_outputs(
    frame: pd.DataFrame,
    output_dir: Path,
    selection: dict[str, Any] | None,
    source: Path,
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(frame)
    frame.sort_values(
        ["configuration", "language", "context_size_k", "model_id", "instance_id", "trial_id"]
    ).to_csv(output_dir / "repoqa_trials.csv", index=False)
    summary.to_csv(output_dir / "repoqa_summary_by_configuration.csv", index=False)
    for dimension, name in (
        ("model", "repoqa_summary_by_model.csv"),
        ("language", "repoqa_summary_by_language.csv"),
        ("context_size_k", "repoqa_summary_by_context_size.csv"),
    ):
        summarize_dimension(frame, dimension).to_csv(output_dir / name, index=False)
    frame[frame["passed"].eq(False) | frame["hit"].eq(False)].to_csv(
        output_dir / "repoqa_failures.csv", index=False
    )
    incomplete = frame.loc[~frame["analysis_complete"].fillna(False).astype(bool)]
    incomplete.to_csv(output_dir / "repoqa_incomplete_trials.csv", index=False)
    manifest = {
        "sourceDirectory": str(source),
        "selection": selection,
        "joinedTrials": int(len(frame)),
        "completeTrials": int(frame["analysis_complete"].fillna(False).sum()),
        "incompleteTrials": int((~frame["analysis_complete"].fillna(False).astype(bool)).sum()),
        "configurations": {
            str(key): int(value) for key, value in frame.groupby("configuration").size().items()
        },
        "models": sorted(str(value) for value in frame["model"].dropna().unique()),
        "languages": sorted(str(value) for value in frame["language"].dropna().unique()),
        "contextSizesK": sorted(int(value) for value in frame["context_size_k"].dropna().unique()),
        "note": "All metrics are derived directly from preserved RepoQA artifacts.",
    }
    (output_dir / "repoqa_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "experiment_dir",
        type=Path,
        nargs="?",
        default=Path("experiments/repoqa/baseline-01"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--selection", type=Path, default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any response lacks a complete RepoQA metric set.",
    )
    args = parser.parse_args()

    experiment_dir = args.experiment_dir.resolve()
    output_dir = (args.output_dir or experiment_dir / "derived" / "analysis").resolve()
    try:
        frame = load_trials(experiment_dir, strict=args.strict)
        frame, selection = apply_selection(
            frame, args.selection.resolve() if args.selection else None
        )
        summary = write_outputs(frame, output_dir, selection, experiment_dir)
    except (ArtifactError, OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        summary[
            ["Config", "N", "CompleteN", "Hit", "Pass", "Sim.", "Tok./T", "Tok./P", "Sec.", "Calls"]
        ].to_string(index=False)
    )
    print(f"Wrote RepoQA analysis to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
