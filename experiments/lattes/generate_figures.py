#!/usr/bin/env python3
"""Generate Lattes figures exclusively from preserved baseline artifacts.

The script delegates data loading and metric computation to analyze_lattes.py.
It does not contain paper result values and does not generate the discarded
Pareto chart. Configuration and question orders are derived from the baseline
and its experiment configuration.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from analyze_lattes import config_order, load_runs, question_order


def save_figure(fig: plt.Figure, output_dir: Path, stem: str, dpi: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("pdf", "png", "svg"):
        path = output_dir / f"{stem}.{suffix}"
        kwargs = {"bbox_inches": "tight"}
        if suffix == "png":
            kwargs["dpi"] = dpi
        fig.savefig(path, **kwargs)
        print(f"Wrote {path}")
    plt.close(fig)


def make_strategy_heatmap(
    runs: pd.DataFrame,
    experiment_dir: Path,
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    questions = question_order(experiment_dir, runs)
    configurations = config_order(runs)
    matrix = (
        runs.pivot_table(
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
    image = ax.imshow(matrix.values, aspect="auto", vmin=0, vmax=100, interpolation="nearest", cmap=muted_blue)
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
    runs: pd.DataFrame,
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    configurations = config_order(runs)
    data = [runs.loc[runs["configuration"] == config, "query_duration_sec"].dropna().to_numpy() for config in configurations]
    latency_summary = (
        runs.groupby("configuration")["query_duration_sec"]
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
    runs: pd.DataFrame,
    experiment_dir: Path,
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    questions = question_order(experiment_dir, runs)
    summary = (
        runs.groupby("question_id", as_index=False)
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
    parser.add_argument("experiment_dir", type=Path, nargs="?", default=Path("experiments/lattes/baseline_001"))
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

    experiment_dir = args.experiment_dir.resolve()
    output_dir = (args.output_dir or experiment_dir / "derived" / "figures").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runs, _ = load_runs(experiment_dir, derived_dir=experiment_dir / "derived")
    selected = set(args.only or ["heatmap", "latency", "disagreement"])

    if "heatmap" in selected:
        make_strategy_heatmap(runs, experiment_dir, output_dir, width=args.heatmap_width, height=args.heatmap_height, dpi=args.dpi)
    if "latency" in selected:
        make_latency_boxplot(runs, output_dir, width=args.boxplot_width, height=args.boxplot_height, dpi=args.dpi)
    if "disagreement" in selected:
        make_question_disagreement(runs, experiment_dir, output_dir, width=args.disagreement_width, height=args.disagreement_height, dpi=args.dpi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
