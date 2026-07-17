#!/usr/bin/env python3
"""Analyze the preserved Lattes baseline directly from committed artifacts.

This module is the single source of truth for Lattes-derived tables and figure
inputs. It reads answers.jsonl and judge_votes.jsonl, extracts observed
operation calls from the committed traces, and computes all reported metrics.
Published values may be supplied only as optional verification fixtures; they
are never used as analysis inputs.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from extract_observed_calls import extract as extract_observed_calls

CONFIG_LABELS = {
    ("inline", "html"): "I-HTML",
    ("inline", "json"): "I-JSON",
    ("local_function", "json"): "Func.",
    ("local_function", "html"): "Func.",
    ("local_mcp", "json"): "L-MCP",
    ("local_mcp", "html"): "L-MCP",
    ("mcp", "json"): "R-MCP",
    ("mcp", "html"): "R-MCP",
    ("remote_mcp", "json"): "R-MCP",
    ("remote_mcp", "html"): "R-MCP",
}
PREFERRED_CONFIG_ORDER = ["I-HTML", "I-JSON", "Func.", "L-MCP", "R-MCP"]


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
                raise ArtifactError(f"Expected JSON object in {path}:{line_number}")
            yield value


def nested(payload: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def as_number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def first_number(*values: Any) -> float:
    for value in values:
        parsed = as_number(value)
        if not math.isnan(parsed):
            return parsed
    return math.nan


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return [str(item) for item in parsed] if isinstance(parsed, list) else [value]
    return [str(value)]


def configuration_label(strategy: Any, context_format: Any) -> str:
    strategy_text = str(strategy or "").lower()
    format_text = str(context_format or "").lower()
    known = CONFIG_LABELS.get((strategy_text, format_text))
    if known:
        return known
    if strategy_text in {"local_function", "local_mcp", "mcp", "remote_mcp"}:
        return {
            "local_function": "Func.",
            "local_mcp": "L-MCP",
            "mcp": "R-MCP",
            "remote_mcp": "R-MCP",
        }[strategy_text]
    return f"{strategy_text or 'unknown'}:{format_text or 'unknown'}"


def ordered_present(values: Sequence[str], preferred: Sequence[str]) -> list[str]:
    unique = list(dict.fromkeys(str(value) for value in values if value is not None))
    return [value for value in preferred if value in unique] + sorted(
        value for value in unique if value not in preferred
    )


def experiment_config_path(experiment_dir: Path) -> Path | None:
    candidates = [
        experiment_dir.parent / "experiment.baseline001.json",
        experiment_dir / "experiment.baseline001.json",
        experiment_dir / "experiment.original.json",
    ]
    return next((path for path in candidates if path.is_file()), None)


def question_order(experiment_dir: Path, runs: pd.DataFrame) -> list[str]:
    config_path = experiment_config_path(experiment_dir)
    if config_path:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        questions = nested(payload, "scope", "questions", default=[])
        if isinstance(questions, list):
            present = set(runs["question_id"].astype(str))
            order = [str(item) for item in questions if str(item) in present]
            if order:
                return order + sorted(present.difference(order))
    return list(dict.fromkeys(runs["question_id"].astype(str)))


def config_order(runs: pd.DataFrame) -> list[str]:
    return ordered_present(runs["configuration"].astype(str).tolist(), PREFERRED_CONFIG_ORDER)


def rating(criteria: Any, name: str) -> str | None:
    if not isinstance(criteria, Mapping):
        return None
    item = criteria.get(name)
    if not isinstance(item, Mapping):
        return None
    value = item.get("rating")
    return str(value) if value is not None else None


def _load_call_counts(experiment_dir: Path, derived_dir: Path) -> pd.DataFrame:
    call_dir = derived_dir / "calls"
    by_run_path, _, _ = extract_observed_calls(experiment_dir, call_dir)
    calls = pd.read_csv(by_run_path)
    if calls.empty:
        return pd.DataFrame(columns=["runId", "observed_calls", "call_source", "trace_exists"])
    calls["observed_calls"] = pd.to_numeric(calls["observedCallCount"], errors="coerce").fillna(0)
    return calls.rename(
        columns={"observedCallSource": "call_source", "traceExists": "trace_exists"}
    )[["runId", "observed_calls", "call_source", "trace_exists"]]


def load_runs(
    experiment_dir: Path,
    *,
    derived_dir: Path | None = None,
    strict: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    experiment_dir = experiment_dir.resolve()
    derived_dir = (derived_dir or experiment_dir / "derived").resolve()

    answers = list(read_jsonl(experiment_dir / "answers.jsonl"))
    votes = list(read_jsonl(experiment_dir / "judge_votes.jsonl"))
    if not answers or not votes:
        raise ArtifactError("answers.jsonl and judge_votes.jsonl must not be empty")

    vote_rows: list[dict[str, Any]] = []
    for vote in votes:
        correctness = rating(vote.get("criterias"), "correctness")
        completeness = rating(vote.get("criterias"), "completeness")
        vote_rows.append(
            {
                "runId": vote.get("runId"),
                "judge_id": vote.get("judgeId"),
                "judge_provider": vote.get("provider"),
                "judge_model": vote.get("model"),
                "question_id": vote.get("questionId"),
                "instance_id": vote.get("instanceId"),
                "strategy": vote.get("strategy"),
                "correctness_rating": correctness,
                "completeness_rating": completeness,
                "correctness_meets": correctness == "meets",
                "completeness_meets": completeness == "meets",
                "both_meet": correctness == "meets" and completeness == "meets",
                "judge_tokens": first_number(vote.get("totalTokens")),
                "judge_duration_sec": first_number(vote.get("durationMs")) / 1000.0,
                "status": vote.get("status"),
            }
        )
    vote_frame = pd.DataFrame(vote_rows)
    if vote_frame["runId"].isna().any():
        raise ArtifactError("judge_votes.jsonl contains votes without runId")

    aggregated = (
        vote_frame.groupby("runId", as_index=False)
        .agg(
            judge_count=("judge_id", "nunique"),
            both_meet_votes=("both_meet", "sum"),
            correctness_meets_votes=("correctness_meets", "sum"),
            completeness_meets_votes=("completeness_meets", "sum"),
            correctness_label_count=("correctness_rating", "nunique"),
            completeness_label_count=("completeness_rating", "nunique"),
        )
    )
    aggregated["majority_correct"] = aggregated["both_meet_votes"] >= 2
    aggregated["unanimous_correct"] = aggregated["both_meet_votes"] == aggregated["judge_count"]
    aggregated["majority_correctness"] = aggregated["correctness_meets_votes"] >= 2
    aggregated["majority_completeness"] = aggregated["completeness_meets_votes"] >= 2
    aggregated["full_disagreement"] = (
        aggregated["correctness_label_count"].eq(3)
        | aggregated["completeness_label_count"].eq(3)
    )

    run_rows: list[dict[str, Any]] = []
    for answer in answers:
        metrics = answer.get("metricsSummary") if isinstance(answer.get("metricsSummary"), Mapping) else {}
        usage = answer.get("usage") if isinstance(answer.get("usage"), Mapping) else {}
        timing = answer.get("timing") if isinstance(answer.get("timing"), Mapping) else {}
        strategy = answer.get("strategy")
        context_format = answer.get("format")
        run_rows.append(
            {
                "runId": answer.get("runId"),
                "experiment_id": answer.get("experimentId"),
                "instance_id": answer.get("instanceId"),
                "question_id": answer.get("questionId"),
                "question_tags": normalize_tags(answer.get("questionTags")),
                "provider": answer.get("provider"),
                "model_id": answer.get("modelId"),
                "model": answer.get("model"),
                "strategy": strategy,
                "format": context_format,
                "configuration": configuration_label(strategy, context_format),
                "repeat_index": answer.get("repeatIndex"),
                "status": answer.get("status"),
                "trace_ref": answer.get("traceRef"),
                "query_total_tokens": first_number(metrics.get("totalTokens"), usage.get("totalTokens")),
                "query_input_tokens_reported": first_number(metrics.get("inputTokens"), usage.get("inputTokens")),
                "query_output_tokens": first_number(metrics.get("outputTokens"), usage.get("outputTokens")),
                "query_duration_sec": first_number(metrics.get("totalDurationMs"), timing.get("durationMs")) / 1000.0,
                "model_calls": first_number(metrics.get("modelCalls")),
                "metric_tool_calls": first_number(metrics.get("toolCalls")),
                "metric_function_calls": first_number(metrics.get("functionCalls")),
                "metric_mcp_calls": first_number(metrics.get("mcpToolCalls")),
                "context_chars": first_number(metrics.get("contextChars")),
                "prompt_chars": first_number(metrics.get("promptChars")),
            }
        )
    runs = pd.DataFrame(run_rows)
    if runs["runId"].isna().any() or runs["runId"].duplicated().any():
        raise ArtifactError("answers.jsonl must contain one unique runId per record")

    runs = runs.merge(aggregated, on="runId", how="left", validate="one_to_one")
    calls = _load_call_counts(experiment_dir, derived_dir)
    runs = runs.merge(calls, on="runId", how="left", validate="one_to_one")
    runs["observed_calls"] = runs["observed_calls"].fillna(0.0)

    required = [
        "query_total_tokens",
        "query_duration_sec",
        "judge_count",
        "majority_correct",
        "unanimous_correct",
    ]
    if strict:
        for column in required:
            missing = int(runs[column].isna().sum())
            if missing:
                raise ArtifactError(f"{missing} baseline rows have missing {column}")
        if not runs["judge_count"].eq(3).all():
            counts = runs["judge_count"].value_counts(dropna=False).to_dict()
            raise ArtifactError(f"Expected three judge votes per run, found {counts}")

    for column in [
        "majority_correct",
        "unanimous_correct",
        "majority_correctness",
        "majority_completeness",
        "full_disagreement",
    ]:
        runs[column] = runs[column].fillna(False).astype(bool)
    return runs, vote_frame


def summarize_configurations(runs: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for config, group in runs.groupby("configuration", sort=False):
        n = len(group)
        majority_count = int(group["majority_correct"].sum())
        unanimous_count = int(group["unanimous_correct"].sum())
        tokens = float(group["query_total_tokens"].sum())
        records.append(
            {
                "Config": config,
                "N": n,
                "Maj.": group["majority_correct"].mean() * 100,
                "Unan.": group["unanimous_correct"].mean() * 100,
                "Tok./T": tokens / n,
                "Tok./M": tokens / majority_count if majority_count else math.nan,
                "Tok./U": tokens / unanimous_count if unanimous_count else math.nan,
                "Sec.": group["query_duration_sec"].median(),
                "Calls": group["observed_calls"].mean(),
                "MajorityCount": majority_count,
                "UnanimousCount": unanimous_count,
            }
        )
    summary = pd.DataFrame(records)
    order = {name: index for index, name in enumerate(config_order(runs))}
    summary["_order"] = summary["Config"].map(order).fillna(len(order))
    return summary.sort_values(["_order", "Config"]).drop(columns="_order").reset_index(drop=True)


def summarize_by(runs: pd.DataFrame, dimension: str) -> pd.DataFrame:
    result = (
        runs.groupby([dimension, "configuration"], dropna=False)
        .agg(
            N=("runId", "size"),
            Majority=("majority_correct", "mean"),
            Unanimous=("unanimous_correct", "mean"),
            MeanTokens=("query_total_tokens", "mean"),
            MedianSec=("query_duration_sec", "median"),
            MeanCalls=("observed_calls", "mean"),
        )
        .reset_index()
    )
    result["Majority"] *= 100
    result["Unanimous"] *= 100
    return result


def summarize_judges(votes: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    metadata = runs[["runId", "configuration", "model", "provider"]].rename(
        columns={"model": "generation_model", "provider": "generation_provider"}
    )
    joined = votes.merge(metadata, on="runId", how="left", validate="many_to_one")
    return (
        joined.groupby(["judge_id", "judge_provider", "judge_model", "configuration"], dropna=False)
        .agg(
            N=("runId", "size"),
            CorrectnessMeets=("correctness_meets", "mean"),
            CompletenessMeets=("completeness_meets", "mean"),
            BothMeet=("both_meet", "mean"),
            MeanJudgeTokens=("judge_tokens", "mean"),
            MedianJudgeSec=("judge_duration_sec", "median"),
        )
        .reset_index()
        .assign(
            CorrectnessMeets=lambda frame: frame["CorrectnessMeets"] * 100,
            CompletenessMeets=lambda frame: frame["CompletenessMeets"] * 100,
            BothMeet=lambda frame: frame["BothMeet"] * 100,
        )
    )


def summarize_tags(runs: pd.DataFrame) -> pd.DataFrame:
    exploded = runs[["runId", "configuration", "question_tags", "majority_correct", "unanimous_correct"]].explode("question_tags")
    exploded = exploded[exploded["question_tags"].notna() & exploded["question_tags"].ne("")]
    if exploded.empty:
        return pd.DataFrame(columns=["question_tags", "configuration", "N", "Majority", "Unanimous"])
    result = (
        exploded.groupby(["question_tags", "configuration"], dropna=False)
        .agg(N=("runId", "size"), Majority=("majority_correct", "mean"), Unanimous=("unanimous_correct", "mean"))
        .reset_index()
    )
    result["Majority"] *= 100
    result["Unanimous"] *= 100
    return result


def format_k(value: float) -> str:
    return "--" if math.isnan(float(value)) else f"{float(value) / 1000:.1f}k"


def paper_table(summary: pd.DataFrame) -> pd.DataFrame:
    result = summary[["Config", "N", "Maj.", "Unan.", "Tok./T", "Tok./M", "Tok./U", "Sec.", "Calls"]].copy()
    result["Maj."] = result["Maj."].map(lambda value: f"{value:.1f}")
    result["Unan."] = result["Unan."].map(lambda value: f"{value:.1f}")
    for column in ["Tok./T", "Tok./M", "Tok./U"]:
        result[column] = result[column].map(format_k)
    result["Sec."] = result["Sec."].map(lambda value: f"{value:.2f}")
    result["Calls"] = result["Calls"].map(lambda value: f"{value:.2f}")
    return result


def write_latex(table: pd.DataFrame, path: Path) -> None:
    lines = [
        r"\begin{tabular}{lrrrrrrrr}",
        r"\toprule",
        " & ".join(table.columns) + r" \\",
        r"\midrule",
    ]
    for record in table.to_dict(orient="records"):
        lines.append(" & ".join(str(record[column]) for column in table.columns) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def expected_number(value: Any) -> float:
    text = str(value).strip()
    if not text or text == "--":
        return math.nan
    multiplier = 1000 if text.lower().endswith("k") else 1
    return float(text[:-1] if multiplier == 1000 else text) * multiplier


def verify(summary: pd.DataFrame, expected_path: Path) -> list[str]:
    expected = pd.read_csv(expected_path, dtype=str).fillna("")
    actual = {row["Config"]: row for row in summary.to_dict(orient="records")}
    tolerances = {
        "Maj.": 0.15,
        "Unan.": 0.15,
        "Tok./T": 150,
        "Tok./M": 150,
        "Tok./U": 150,
        "Sec.": 0.11,
        "Calls": 0.025,
    }
    errors: list[str] = []
    for expected_row in expected.to_dict(orient="records"):
        config = str(expected_row["Config"])
        actual_row = actual.get(config)
        if actual_row is None:
            errors.append(f"Missing configuration {config}")
            continue
        if int(actual_row["N"]) != int(expected_row["N"]):
            errors.append(f"{config} N: expected {expected_row['N']}, got {actual_row['N']}")
        for metric, tolerance in tolerances.items():
            expected_value = expected_number(expected_row[metric])
            actual_value = float(actual_row[metric])
            if math.isnan(actual_value) or abs(actual_value - expected_value) > tolerance:
                errors.append(f"{config} {metric}: expected {expected_value:g}, got {actual_value:g}")
    return errors


def write_outputs(
    runs: pd.DataFrame,
    votes: pd.DataFrame,
    output_dir: Path,
    source_dir: Path,
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_configurations(runs)
    runs.sort_values(["configuration", "question_id", "instance_id", "model_id"]).to_csv(output_dir / "lattes_trials.csv", index=False)
    summary.to_csv(output_dir / "lattes_summary_by_configuration.csv", index=False)
    summarize_by(runs, "model").to_csv(output_dir / "lattes_summary_by_model.csv", index=False)
    summarize_by(runs, "question_id").to_csv(output_dir / "lattes_summary_by_question.csv", index=False)
    summarize_by(runs, "instance_id").to_csv(output_dir / "lattes_summary_by_curriculum.csv", index=False)
    summarize_tags(runs).to_csv(output_dir / "lattes_summary_by_tag.csv", index=False)
    summarize_judges(votes, runs).to_csv(output_dir / "lattes_summary_by_judge.csv", index=False)

    table = paper_table(summary)
    table.to_csv(output_dir / "tool-paper-table-3a.csv", index=False)
    write_latex(table, output_dir / "tool-paper-table-3a.tex")

    manifest = {
        "sourceDirectory": str(source_dir),
        "sourceArtifacts": ["answers.jsonl", "judge_votes.jsonl", "traces/queries/"],
        "runCount": int(len(runs)),
        "voteCount": int(len(votes)),
        "configurations": {str(key): int(value) for key, value in runs.groupby("configuration").size().items()},
        "models": sorted(str(value) for value in runs["model"].dropna().unique()),
        "questions": question_order(source_dir, runs),
        "instances": sorted(str(value) for value in runs["instance_id"].dropna().unique()),
        "note": "Expected paper values, when supplied, are verification fixtures only and are never read while computing metrics.",
    }
    (output_dir / "lattes_analysis_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_dir", type=Path, nargs="?", default=Path("experiments/lattes/baseline_001"))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--expected", type=Path, default=None, help="Optional paper-value fixture used only after analysis for verification.")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    experiment_dir = args.experiment_dir.resolve()
    output_dir = (args.output_dir or experiment_dir / "derived" / "analysis").resolve()
    try:
        runs, votes = load_runs(
            experiment_dir,
            derived_dir=experiment_dir / "derived",
            strict=not args.allow_incomplete,
        )
        summary = write_outputs(runs, votes, output_dir, experiment_dir)
    except (ArtifactError, OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    columns = ["Config", "N", "Maj.", "Unan.", "Tok./T", "Tok./M", "Tok./U", "Sec.", "Calls"]
    print(summary[columns].to_string(index=False))
    print(f"Wrote Lattes analysis to {output_dir}")

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
