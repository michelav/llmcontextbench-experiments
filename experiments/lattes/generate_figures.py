#!/usr/bin/env python3
"""Generate Lattes figures from analysis files derived from the preserved baseline.

This script deliberately does not read paper tables or embed published result values.
Run ``analyze_lattes.py`` first; it reads the committed baseline artifacts and writes
``lattes_trials.csv`` plus a manifest. Figures are then generated exclusively from
those derived records. The discarded Pareto figure is intentionally not generated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap


class FigureInputError(RuntimeError):
    """Raised when required baseline-derived analysis files are unavailable."""


def save_figure(fig: plt.Figure, output_dir: Path, stem: str, dpi: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("pdf", "png", "svg"):
        path = output_dir / f"{stem}.{suffix}"
        kwargs: dict[str, Any] = {"bbox_inches": "tight"}
        if suffix == "png":
            kwargs["dpi"] = dpi
        fig.savefig(path, **kwargs)
        print(f"Wrote {path}")
    plt.close(fig)


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FigureInputError(f"Missing analysis manifest: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FigureInputError(f"Expected a JSON object in {path}")
    return payload


def parse_boolean(series: pd.Series, column: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    valid = normalized.isin({"true", "false", "1", "0"})
    if not valid.all():
        values = sorted(normalized.loc[~valid].unique())
        raise FigureInputError(f"Invalid boolean values in {column}: {values}")
    return normalized.isin({"true", "1"})


def load_analysis(analysis_dir: Path) -> tuple[pd.DataFrame, list[str], list[str]]:
    trials_path = analysis_dir / "lattes_trials.csv"
    summary_path = analysis_dir / "lattes_summary_by_configuration.csv"
    manifest_path = analysis_dir / "lattes_analysis_manifest.json"

    for path in (trials_path, summary_path, manifest_path):
        if not path.is_file():
            raise FigureInputError(
                f"Missing baseline-derived analysis file: {path}. "
                "Run experiments/lattes/analyze_lattes.py first."
            )

    trials = pd.read_csv(trials_path)
    summary = pd.read_csv(summary_path)
    manifest = read_manifest(manifest_path)

    required = {
        "question_id",
        "configuration",
        "query_duration_sec",
        "majority_correct",
        "unanimous_correct",
        "full_disagreement",
    }
    missing = sorted(required.difference(trials.columns))
    if missing:
        raise FigureInputError(f"{trials_path} is missing columns: {', '.join(missing)}")
    if "Config" not in summary.columns:
        raise FigureInputError(f"{summary_path} is missing the Config column")

    for column in ("majority_correct", "unanimous_correct", "full_disagreement"):
        trials[column] = parse_boolean(trials[column], column)
    trials["query_duration_sec"] = pd.to_numeric(trials["query_duration_sec"], errors="raise")
    trials["question_id"] = trials["question_id"].astype(str)
    trials["configuration"] = trials["configuration"].astype(str)

    present_questions = set(trials["question_id"])
    manifest_questions = [str(value) for value in manifest.get("questions", [])]
    questions = [value for value in manifest_questions if value in present_questions]
    questions.extend(sorted(present_questions.difference(questions)))

    present_configs = set(trials["configuration"])
    configurations = [str(value) for value in summary["Config"] if str(value) in present_configs]
    configurations.extend(sorted(present_configs.difference(configurations)))

    if not questions or not configurations:
        raise FigureInputError("The derived trial table contains no questions or configurations")
    return trials, questions, configurations


def make_strategy_heatmap(
    trials: pd.DataFrame,
    questions: list[str],
    configurations: list[str],
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    matrix = (
        trials.pivot_table(
            index="question_id",
            columns="configuration",
            values="majority_correct",
            aggfunc="mean",
        )
        .reindex(index=questions, columns=configurations)
        * 100
    )
    matrix.to_csv(output_dir / "rq3_question_strategy_heatmap_data.csv")

    muted_blue = LinearSegmentedColormap.from_list(
        "muted_blue",
        ["#f8f8f8", "#edf3f8", "#d9e8f2", "#b8d3e5", "#82b4d2", "#4f8fbd"],
        N=256,
    )
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    image = ax.imshow(
        matrix.values,
        aspect="auto",
        vmin=0,
        vmax=100,
        interpolation="nearest",
        cmap=muted_blue,
    )
    ax.set_xticks(np.arange(len(configurations)))
    ax.set_xticklabels(configurations, fontsize=7.8)
    ax.set_yticks(np.arange(len(questions)))
    ax.set_yticklabels(questions, fontsize=7.2)
    ax.set_title("Majority accuracy by question and strategy", fontsize=9.5)
    ax.set_xlabel("Context provisioning configuration", fontsize=8.3)
    ax.set_ylabel("Question", fontsize=8.3)
    ax.set_xticks(np.arange(-0.5, len(configurations), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(questions), 1), minor=True)
    ax.grid(which="minor", color="#ffffff", linewidth=0.9)
    ax.tick_params(which="minor", bottom=False, left=False)

    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix.iloc[row, column]
            label = "--" if pd.isna(value) else f"{value:.0f}"
            text_color = "#222222" if pd.isna(value) or value < 72 else "#ffffff"
            ax.text(column, row, label, ha="center", va="center", fontsize=6.9, color=text_color)

    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    colorbar.set_label("Majority accuracy (%)", fontsize=7.5)
    colorbar.ax.tick_params(labelsize=7.0)
    fig.tight_layout()
    save_figure(fig, output_dir, "rq3_question_strategy_heatmap", dpi)


def make_latency_boxplot(
    trials: pd.DataFrame,
    configurations: list[str],
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    data = [
        trials.loc[trials["configuration"] == config, "query_duration_sec"].dropna().to_numpy()
        for config in configurations
    ]
    latency_summary = (
        trials.groupby("configuration")["query_duration_sec"]
        .agg(["count", "min", "median", "mean", "max"])
        .reindex(configurations)
    )
    latency_summary.to_csv(output_dir / "rq2_latency_boxplot_data.csv")

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    try:
        ax.boxplot(data, tick_labels=configurations, showmeans=True)
    except TypeError:
        ax.boxplot(data, labels=configurations, showmeans=True)
    ax.set_title("Query latency distribution by strategy", fontsize=9.5)
    ax.set_xlabel("Context provisioning configuration", fontsize=8.5)
    ax.set_ylabel("Query duration (s)", fontsize=8.5)
    ax.tick_params(axis="both", labelsize=7.5)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.55)
    fig.tight_layout()
    save_figure(fig, output_dir, "rq2_latency_boxplot_strategy", dpi)


def make_question_disagreement(
    trials: pd.DataFrame,
    questions: list[str],
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    summary = (
        trials.groupby("question_id", as_index=False)
        .agg(
            Majority=("majority_correct", "mean"),
            Unanimous=("unanimous_correct", "mean"),
            FullDisagreement=("full_disagreement", "mean"),
        )
        .set_index("question_id")
        .reindex(questions)
        .reset_index()
    )
    summary["MajorityPct"] = summary["Majority"] * 100
    summary["UnanimousPct"] = summary["Unanimous"] * 100
    summary["FullDisagreementPct"] = summary["FullDisagreement"] * 100
    summary.to_csv(output_dir / "rq3_question_disagreement_data.csv", index=False)

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    y = np.arange(len(summary))
    ax.scatter(summary["MajorityPct"], y, s=38, label="Majority")
    ax.scatter(summary["UnanimousPct"], y, s=38, marker="s", label="Unanimous")
    ax.scatter(summary["FullDisagreementPct"], y, s=38, marker="^", label="Full disagreement")
    ax.set_yticks(y)
    ax.set_yticklabels(summary["question_id"], fontsize=7.2)
    ax.invert_yaxis()
    ax.set_xlabel("Runs (%)", fontsize=8.5)
    ax.set_title("Question difficulty and judge disagreement", fontsize=9.5)
    ax.tick_params(axis="x", labelsize=7.5)
    ax.grid(True, axis="x", linestyle=":", linewidth=0.55)
    ax.legend(fontsize=7.3, loc="lower right")
    fig.tight_layout()
    save_figure(fig, output_dir, "rq3_question_difficulty_disagreement", dpi)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "analysis_dir",
        type=Path,
        nargs="?",
        default=Path("experiments/lattes/baseline_001/derived/analysis"),
        help="Directory produced by analyze_lattes.py.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--heatmap-width", type=float, default=6.35)
    parser.add_argument("--heatmap-height", type=float, default=3.65)
    parser.add_argument("--boxplot-width", type=float, default=5.0)
    parser.add_argument("--boxplot-height", type=float, default=3.0)
    parser.add_argument("--disagreement-width", type=float, default=5.0)
    parser.add_argument("--disagreement-height", type=float, default=3.2)
    parser.add_argument("--only", nargs="*", choices=["heatmap", "latency", "disagreement"], default=None)
    args = parser.parse_args()

    analysis_dir = args.analysis_dir.resolve()
    output_dir = (args.output_dir or analysis_dir.parent / "figures").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        trials, questions, configurations = load_analysis(analysis_dir)
    except (FigureInputError, OSError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    selected = set(args.only or ["heatmap", "latency", "disagreement"])
    if "heatmap" in selected:
        make_strategy_heatmap(
            trials,
            questions,
            configurations,
            output_dir,
            width=args.heatmap_width,
            height=args.heatmap_height,
            dpi=args.dpi,
        )
    if "latency" in selected:
        make_latency_boxplot(
            trials,
            configurations,
            output_dir,
            width=args.boxplot_width,
            height=args.boxplot_height,
            dpi=args.dpi,
        )
    if "disagreement" in selected:
        make_question_disagreement(
            trials,
            questions,
            output_dir,
            width=args.disagreement_width,
            height=args.disagreement_height,
            dpi=args.dpi,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
