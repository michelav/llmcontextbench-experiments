#!/usr/bin/env python3
"""Analyze the preserved Lattes baseline directly from committed artifacts.

This module is the single source of truth for Lattes-derived tables and figure
inputs. It reads answers.jsonl and judge_votes.jsonl, enriches question metadata
from queries.jsonl when needed, extracts observed operation calls from committed
traces, and computes all reported metrics. Published values may be supplied only
as optional verification fixtures; they are never used as analysis inputs.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
CONFIG_STRATEGY_LABELS = {
    "I-HTML": "Inline HTML",
    "I-JSON": "Inline JSON",
    "Func.": "Local function calling",
    "L-MCP": "Local MCP",
    "R-MCP": "Remote MCP",
}

# This is the top-to-bottom order used in Figure 3b and Table 7 of the
# research-track paper. It is presentation metadata, not a source of results.
PAPER_QUESTION_ORDER = [
    "q_field",
    "q_projfit_2",
    "q_indexed",
    "q_en",
    "q_techprod",
    "q_phd",
    "q_admin",
    "q_pubyear",
    "q_advpub",
    "q_coauth",
    "q_tcc5y",
    "q_sup",
]

# Qualitative interpretations reported in Table 7. All numerical columns in
# that table are computed from the preserved baseline.
QUESTION_DIFFICULTY = {
    "q_field": "broad profile synthesis",
    "q_projfit_2": "cross-section project matching",
    "q_indexed": "weak evidence and count interpretation",
    "q_en": "simple lookup; mostly stable",
    "q_techprod": "weakly structured technical output",
    "q_phd": "temporal education lookup",
    "q_admin": "administrative-role evidence",
    "q_pubyear": "temporal publication ranking",
    "q_advpub": "supervision–publication matching",
    "q_coauth": "coauthor aggregation and ranking",
    "q_tcc5y": "temporal counting over supervision records",
    "q_sup": "counting over unstructured supervision records",
}

MODEL_LABELS = {
    "gpt-5.4-nano": "GPT-Nano",
    "gpt-5.4-mini": "GPT-Mini",
    "gemini-2.5-flash-lite": "Gemini-Lite",
    "gemini-2.5-flash": "Gemini-Flash",
}
MODEL_ID_LABELS = {
    "gpt1": "GPT-Nano",
    "gpt2": "GPT-Mini",
    "gemini1": "Gemini-Lite",
    "gemini2": "Gemini-Flash",
}
PREFERRED_MODEL_ORDER = ["GPT-Nano", "GPT-Mini", "Gemini-Lite", "Gemini-Flash"]


class ArtifactError(RuntimeError):
    """Raised when preserved experiment artifacts are inconsistent."""


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
    if isinstance(value, (list, tuple)):
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


def question_order(runs: pd.DataFrame) -> list[str]:
    return ordered_present(runs["question_id"].astype(str).tolist(), PAPER_QUESTION_ORDER)


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


def display_model_label(model: Any, model_id: Any) -> str:
    model_text = str(model or "")
    model_id_text = str(model_id or "")
    if model_text in MODEL_LABELS:
        return MODEL_LABELS[model_text]
    if model_id_text in MODEL_ID_LABELS:
        return MODEL_ID_LABELS[model_id_text]

    lower = model_text.lower()
    if "gemini" in lower and "lite" in lower:
        return "Gemini-Lite"
    if "gemini" in lower and "flash" in lower:
        return "Gemini-Flash"
    if "gpt" in lower and "nano" in lower:
        return "GPT-Nano"
    if "gpt" in lower and "mini" in lower:
        return "GPT-Mini"
    return model_text or model_id_text or "Unknown"


def display_family(provider: Any, model_label: str) -> str:
    provider_text = str(provider or "").strip().lower()
    if provider_text in {"openai", "open_ai"} or model_label.startswith("GPT-"):
        return "OpenAI"
    if provider_text in {"google", "gemini"} or model_label.startswith("Gemini-"):
        return "Gemini"
    return str(provider or "Unknown")


def _query_metadata(experiment_dir: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return question tags indexed by run and by question.

    answers.jsonl is authoritative for execution results. queries.jsonl is used
    only to recover static question metadata when historical answer records omit
    questionTags.
    """

    path = experiment_dir / "queries.jsonl"
    if not path.is_file():
        return {}, {}

    by_run: dict[str, list[str]] = {}
    by_question: dict[str, list[str]] = {}
    for row in read_jsonl(path):
        tags = normalize_tags(
            row.get("questionTags", row.get("tags", nested(row, "question", "tags")))
        )
        run_id = row.get("runId")
        question_id = row.get("questionId", nested(row, "question", "id"))
        if run_id is not None and tags:
            by_run[str(run_id)] = tags
        if question_id is not None and tags:
            key = str(question_id)
            previous = by_question.get(key)
            if previous is not None and previous != tags:
                raise ArtifactError(f"Inconsistent tags for question {key} in queries.jsonl")
            by_question[key] = tags
    return by_run, by_question


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

    tags_by_run, tags_by_question = _query_metadata(experiment_dir)
    run_rows: list[dict[str, Any]] = []
    for answer in answers:
        metrics = answer.get("metricsSummary") if isinstance(answer.get("metricsSummary"), Mapping) else {}
        usage = answer.get("usage") if isinstance(answer.get("usage"), Mapping) else {}
        timing = answer.get("timing") if isinstance(answer.get("timing"), Mapping) else {}
        strategy = answer.get("strategy")
        context_format = answer.get("format")
        run_id = answer.get("runId")
        question_id = answer.get("questionId")
        tags = normalize_tags(answer.get("questionTags", nested(answer, "question", "tags")))
        if not tags and run_id is not None:
            tags = tags_by_run.get(str(run_id), [])
        if not tags and question_id is not None:
            tags = tags_by_question.get(str(question_id), [])

        run_rows.append(
            {
                "runId": run_id,
                "experiment_id": answer.get("experimentId"),
                "instance_id": answer.get("instanceId"),
                "question_id": question_id,
                "question_tags": tags,
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
    exploded = runs[
        ["runId", "configuration", "question_tags", "majority_correct", "unanimous_correct"]
    ].explode("question_tags")
    exploded = exploded[exploded["question_tags"].notna() & exploded["question_tags"].ne("")]
    if exploded.empty:
        return pd.DataFrame(columns=["question_tags", "configuration", "N", "Majority", "Unanimous"])
    result = (
        exploded.groupby(["question_tags", "configuration"], dropna=False)
        .agg(
            N=("runId", "size"),
            Majority=("majority_correct", "mean"),
            Unanimous=("unanimous_correct", "mean"),
        )
        .reset_index()
    )
    result["Majority"] *= 100
    result["Unanimous"] *= 100
    return result


def format_k(value: float) -> str:
    return "--" if math.isnan(float(value)) else f"{float(value) / 1000:.1f}k"


def paper_table_5(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in summary.to_dict(orient="records"):
        config = str(row["Config"])
        rows.append(
            {
                "Configuration": config,
                "Strategy": CONFIG_STRATEGY_LABELS.get(config, config),
                "Runs": int(row["N"]),
                "Maj.": f"{float(row['Maj.']):.1f}",
                "Unan.": f"{float(row['Unan.']):.1f}",
                "Tok./run": format_k(float(row["Tok./T"])),
                "Tok./Maj.": format_k(float(row["Tok./M"])),
                "Tok./Unan.": format_k(float(row["Tok./U"])),
                "Sec.": f"{float(row['Sec.']):.2f}",
                "Obs. calls": f"{float(row['Calls']):.2f}",
            }
        )
    return pd.DataFrame(rows)


def paper_table_6(runs: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        runs.groupby(["provider", "model_id", "model", "configuration"], dropna=False)
        .agg(
            Majority=("majority_correct", "mean"),
            Unanimous=("unanimous_correct", "mean"),
            Tokens=("query_total_tokens", "mean"),
            Sec=("query_duration_sec", "median"),
            Calls=("observed_calls", "mean"),
        )
        .reset_index()
    )
    grouped["ModelLabel"] = grouped.apply(
        lambda row: display_model_label(row["model"], row["model_id"]), axis=1
    )
    grouped["Family"] = grouped.apply(
        lambda row: display_family(row["provider"], row["ModelLabel"]), axis=1
    )
    model_order = {name: index for index, name in enumerate(PREFERRED_MODEL_ORDER)}
    config_position = {name: index for index, name in enumerate(PREFERRED_CONFIG_ORDER)}
    family_order = {"OpenAI": 0, "Gemini": 1}
    grouped["_family"] = grouped["Family"].map(family_order).fillna(len(family_order))
    grouped["_model"] = grouped["ModelLabel"].map(model_order).fillna(len(model_order))
    grouped["_config"] = grouped["configuration"].map(config_position).fillna(len(config_position))
    grouped = grouped.sort_values(["_family", "_model", "_config", "configuration"])

    return pd.DataFrame(
        {
            "Family": grouped["Family"],
            "Model": grouped["ModelLabel"],
            "Configuration": grouped["configuration"],
            "Maj.": grouped["Majority"].map(lambda value: f"{value * 100:.1f}"),
            "Unan.": grouped["Unanimous"].map(lambda value: f"{value * 100:.1f}"),
            "Tok.": grouped["Tokens"].map(format_k),
            "Sec.": grouped["Sec"].map(lambda value: f"{value:.2f}"),
            "Calls": grouped["Calls"].map(lambda value: f"{value:.2f}"),
        }
    ).reset_index(drop=True)


def _question_tags(group: pd.DataFrame, question_id: str) -> str:
    candidates: list[tuple[str, ...]] = []
    for value in group["question_tags"]:
        tags = tuple(normalize_tags(value))
        if tags and tags not in candidates:
            candidates.append(tags)
    if len(candidates) > 1:
        raise ArtifactError(f"Inconsistent question tags for {question_id}: {candidates}")
    return ", ".join(candidates[0]) if candidates else ""


def paper_table_7(runs: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for question_id, group in runs.groupby("question_id", sort=False):
        question = str(question_id)
        rows.append(
            {
                "Question": question,
                "Tags": _question_tags(group, question),
                "Maj.": f"{group['majority_correct'].mean() * 100:.1f}",
                "Unan.": f"{group['unanimous_correct'].mean() * 100:.1f}",
                "Full dis.": f"{group['full_disagreement'].mean() * 100:.1f}",
                "Calls": f"{group['observed_calls'].mean():.2f}",
                "Dominant difficulty": QUESTION_DIFFICULTY.get(question, ""),
            }
        )
    table = pd.DataFrame(rows)
    order = {name: index for index, name in enumerate(PAPER_QUESTION_ORDER)}
    table["_order"] = table["Question"].map(order).fillna(len(order))
    return table.sort_values(["_order", "Question"]).drop(columns="_order").reset_index(drop=True)


def verify_table_5(actual: pd.DataFrame, expected_path: Path) -> list[str]:
    expected = pd.read_csv(expected_path, dtype=str, keep_default_na=False)
    actual_text = actual.astype(str)
    errors: list[str] = []
    if list(actual_text.columns) != list(expected.columns):
        errors.append(
            f"Columns differ: expected {list(expected.columns)}, got {list(actual_text.columns)}"
        )
        return errors
    if len(actual_text) != len(expected):
        errors.append(f"Row count differs: expected {len(expected)}, got {len(actual_text)}")
        return errors
    for index, (actual_row, expected_row) in enumerate(
        zip(actual_text.to_dict(orient="records"), expected.to_dict(orient="records")),
        start=1,
    ):
        for column in expected.columns:
            if actual_row[column] != expected_row[column]:
                errors.append(
                    f"row {index} {column}: expected {expected_row[column]!r}, "
                    f"got {actual_row[column]!r}"
                )
    return errors


def write_outputs(
    runs: pd.DataFrame,
    votes: pd.DataFrame,
    output_dir: Path,
    source_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_configurations(runs)

    runs.sort_values(["configuration", "question_id", "instance_id", "model_id"]).to_csv(
        output_dir / "lattes_trials.csv", index=False
    )
    summary.to_csv(output_dir / "lattes_summary_by_configuration.csv", index=False)
    summarize_by(runs, "model").to_csv(output_dir / "lattes_summary_by_model.csv", index=False)
    summarize_by(runs, "question_id").to_csv(output_dir / "lattes_summary_by_question.csv", index=False)
    summarize_by(runs, "instance_id").to_csv(output_dir / "lattes_summary_by_curriculum.csv", index=False)
    summarize_tags(runs).to_csv(output_dir / "lattes_summary_by_tag.csv", index=False)
    summarize_judges(votes, runs).to_csv(output_dir / "lattes_summary_by_judge.csv", index=False)

    table_5 = paper_table_5(summary)
    table_6 = paper_table_6(runs)
    table_7 = paper_table_7(runs)
    table_5.to_csv(output_dir / "table-5.csv", index=False)
    table_6.to_csv(output_dir / "table-6.csv", index=False)
    table_7.to_csv(output_dir / "table-7.csv", index=False)

    # Remove obsolete files produced by the previous tool-paper-oriented naming.
    for stale_name in ("tool-paper-table-3a.csv", "tool-paper-table-3a.tex"):
        stale_path = output_dir / stale_name
        if stale_path.exists():
            stale_path.unlink()

    manifest = {
        "sourceDirectory": str(source_dir),
        "sourceArtifacts": [
            "queries.jsonl",
            "answers.jsonl",
            "judge_votes.jsonl",
            "traces/queries/",
        ],
        "runCount": int(len(runs)),
        "voteCount": int(len(votes)),
        "configurations": {
            str(key): int(value) for key, value in runs.groupby("configuration").size().items()
        },
        "models": sorted(str(value) for value in runs["model"].dropna().unique()),
        "questions": question_order(runs),
        "instances": sorted(str(value) for value in runs["instance_id"].dropna().unique()),
        "paperTables": ["table-5.csv", "table-6.csv", "table-7.csv"],
        "paperFigures": [
            "figure-3a-latency-violin",
            "figure-3b-question-accuracy-heatmap",
            "figure-3-combined",
        ],
        "note": (
            "Expected paper values, when supplied, are verification fixtures only "
            "and are never read while computing metrics."
        ),
    }
    (output_dir / "lattes_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return summary, table_5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "experiment_dir",
        type=Path,
        nargs="?",
        default=Path("experiments/lattes/baseline_001"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--expected",
        type=Path,
        default=None,
        help="Optional Table 5 fixture used only after analysis for verification.",
    )
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
        summary, table_5 = write_outputs(runs, votes, output_dir, experiment_dir)
    except (ArtifactError, OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    columns = ["Config", "N", "Maj.", "Unan.", "Tok./T", "Tok./M", "Tok./U", "Sec.", "Calls"]
    print(summary[columns].to_string(index=False))
    print(f"Wrote Lattes analysis to {output_dir}")

    if args.expected:
        errors = verify_table_5(table_5, args.expected.resolve())
        if errors:
            print("Table 5 verification failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1 if args.verify else 0
        print("Table 5 verification passed.")
    elif args.verify:
        print("ERROR: --verify requires --expected", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
