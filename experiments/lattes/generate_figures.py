#!/usr/bin/env python3
"""Generate the Lattes paper figures from baseline-derived CSV files.

Run ``analyze_lattes.py`` first. This script reads only the derived trial table
and manifest; it never reads raw JSONL files, traces, or published paper values.
The primary outputs reproduce Figure 3a (latency violin plot) and Figure 3b
(question-by-configuration majority-accuracy heatmap).
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
PREFERRED_CONFIG_ORDER = ["I-HTML", "I-JSON", "Func.", "L-MCP", "R-MCP"]


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


def ordered_present(values: list[str], preferred: list[str]) -> list[str]:
    present = list(dict.fromkeys(values))
    return [item for item in preferred if item in present] + sorted(
        item for item in present if item not in preferred
    )


def load_analysis(analysis_dir: Path) -> tuple[pd.DataFrame, list[str], list[str]]:
    trials_path = analysis_dir / "lattes_trials.csv"
    manifest_path = analysis_dir / "lattes_analysis_manifest.json"

    for path in (trials_path, manifest_path):
        if not path.is_file():
            raise FigureInputError(
                f"Missing baseline-derived analysis file: {path}. "
                "Run experiments/lattes/analyze_lattes.py first."
            )

    trials = pd.read_csv(trials_path)
    manifest = read_manifest(manifest_path)
    required = {
        "question_id",
        "configuration",
        "query_duration_sec",
        "majority_correct",
    }
    missing = sorted(required.difference(trials.columns))
    if missing:
        raise FigureInputError(f"{trials_path} is missing columns: {', '.join(missing)}")

    trials["majority_correct"] = parse_boolean(trials["majority_correct"], "majority_correct")
    trials["query_duration_sec"] = pd.to_numeric(
        trials["query_duration_sec"], errors="raise"
    )
    trials["question_id"] = trials["question_id"].astype(str)
    trials["configuration"] = trials["configuration"].astype(str)

    present_questions = list(dict.fromkeys(trials["question_id"].tolist()))
    questions = ordered_present(present_questions, PAPER_QUESTION_ORDER)
    present_configs = list(dict.fromkeys(trials["configuration"].tolist()))
    configurations = ordered_present(present_configs, PREFERRED_CONFIG_ORDER)

    manifest_questions = [str(value) for value in manifest.get("questions", [])]
    if manifest_questions and manifest_questions != questions:
        raise FigureInputError(
            "Question order in lattes_analysis_manifest.json does not match the paper order"
        )
    if not questions or not configurations:
        raise FigureInputError("The derived trial table contains no questions or configurations")
    return trials, questions, configurations


def latency_data(
    trials: pd.DataFrame, configurations: list[str]
) -> tuple[list[np.ndarray], pd.DataFrame]:
    data = [
        trials.loc[
            trials["configuration"] == configuration, "query_duration_sec"
        ].dropna().to_numpy()
        for configuration in configurations
    ]
    if any(len(values) == 0 for values in data):
        missing = [
            configuration
            for configuration, values in zip(configurations, data)
            if len(values) == 0
        ]
        raise FigureInputError(f"No latency values for configurations: {missing}")

    summary = (
        trials.groupby("configuration")["query_duration_sec"]
        .agg(["count", "mean", "median", "min", "max"])
        .reindex(configurations)
    )
    return data, summary


def draw_latency_violin(
    ax: plt.Axes,
    trials: pd.DataFrame,
    configurations: list[str],
    *,
    write_data_to: Path | None = None,
) -> None:
    data, summary = latency_data(trials, configurations)
    if write_data_to is not None:
        summary.to_csv(write_data_to)

    positions = np.arange(1, len(configurations) + 1)
    violin = ax.violinplot(
        data,
        positions=positions,
        widths=0.82,
        showmeans=False,
        showmedians=False,
        showextrema=False,
        bw_method="scott",
    )
    for body in violin["bodies"]:
        body.set_facecolor("#d6e4ef")
        body.set_edgecolor("#3f6f8f")
        body.set_alpha(0.9)
        body.set_linewidth(0.8)

    box = ax.boxplot(
        data,
        positions=positions,
        widths=0.18,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#1f1f1f", "linewidth": 1.15},
        boxprops={"facecolor": "#ffffff", "edgecolor": "#1f1f1f", "linewidth": 0.8},
        whiskerprops={"color": "#1f1f1f", "linewidth": 0.8},
        capprops={"color": "#1f1f1f", "linewidth": 0.8},
    )
    del box

    ax.set_xticks(positions)
    ax.set_xticklabels(configurations, fontsize=7.6)
    ax.set_xlabel("Context provisioning configuration", fontsize=8.2)
    ax.set_ylabel("Query duration (s)", fontsize=8.2)
    ax.set_ylim(0, 35)
    ax.set_yticks(np.arange(0, 36, 5))
    ax.tick_params(axis="y", labelsize=7.2)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.5, alpha=0.65)

    for position, configuration in zip(positions, configurations):
        mean = float(summary.loc[configuration, "mean"])
        median = float(summary.loc[configuration, "median"])
        ax.text(
            position,
            33.8,
            f"{configuration}\nmean={mean:.2f}s\nmedian={median:.2f}s",
            ha="center",
            va="top",
            fontsize=6.4,
            linespacing=1.15,
        )


def heatmap_matrix(
    trials: pd.DataFrame,
    questions: list[str],
    configurations: list[str],
) -> pd.DataFrame:
    return (
        trials.pivot_table(
            index="question_id",
            columns="configuration",
            values="majority_correct",
            aggfunc="mean",
        )
        .reindex(index=questions, columns=configurations)
        * 100
    )


def draw_accuracy_heatmap(
    ax: plt.Axes,
    trials: pd.DataFrame,
    questions: list[str],
    configurations: list[str],
    *,
    write_data_to: Path | None = None,
) -> Any:
    matrix = heatmap_matrix(trials, questions, configurations)
    if write_data_to is not None:
        matrix.to_csv(write_data_to)

    muted_blue = LinearSegmentedColormap.from_list(
        "muted_blue",
        ["#f8f8f8", "#edf3f8", "#d9e8f2", "#b8d3e5", "#82b4d2", "#4f8fbd"],
        N=256,
    )
    image = ax.imshow(
        matrix.values,
        aspect="auto",
        vmin=0,
        vmax=100,
        interpolation="nearest",
        cmap=muted_blue,
    )
    ax.set_xticks(np.arange(len(configurations)))
    ax.set_xticklabels(configurations, fontsize=7.6)
    ax.set_yticks(np.arange(len(questions)))
    ax.set_yticklabels(questions, fontsize=7.0)
    ax.set_xlabel("Context provisioning configuration", fontsize=8.2)
    ax.set_ylabel("Question", fontsize=8.2)
    ax.set_title("Majority accuracy by question and strategy", fontsize=9.0)
    ax.set_xticks(np.arange(-0.5, len(configurations), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(questions), 1), minor=True)
    ax.grid(which="minor", color="#ffffff", linewidth=0.9)
    ax.tick_params(which="minor", bottom=False, left=False)

    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix.iloc[row, column]
            label = "--" if pd.isna(value) else f"{value:.0f}"
            text_color = "#222222" if pd.isna(value) or value < 72 else "#ffffff"
            ax.text(
                column,
                row,
                label,
                ha="center",
                va="center",
                fontsize=6.8,
                color=text_color,
            )
    return image


def make_latency_violin(
    trials: pd.DataFrame,
    configurations: list[str],
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    draw_latency_violin(
        ax,
        trials,
        configurations,
        write_data_to=output_dir / "figure-3a-latency-data.csv",
    )
    fig.tight_layout()
    save_figure(fig, output_dir, "figure-3a-latency-violin", dpi)


def make_accuracy_heatmap(
    trials: pd.DataFrame,
    questions: list[str],
    configurations: list[str],
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    image = draw_accuracy_heatmap(
        ax,
        trials,
        questions,
        configurations,
        write_data_to=output_dir / "figure-3b-heatmap-data.csv",
    )
    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    colorbar.set_label("Majority accuracy (%)", fontsize=7.4)
    colorbar.ax.tick_params(labelsize=7.0)
    fig.tight_layout()
    save_figure(fig, output_dir, "figure-3b-question-accuracy-heatmap", dpi)


def make_combined_figure(
    trials: pd.DataFrame,
    questions: list[str],
    configurations: list[str],
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(width, height), dpi=dpi)
    draw_latency_violin(axes[0], trials, configurations)
    image = draw_accuracy_heatmap(axes[1], trials, questions, configurations)
    axes[0].text(0.5, -0.20, "(a)", transform=axes[0].transAxes, ha="center", fontsize=8)
    axes[1].text(0.5, -0.20, "(b)", transform=axes[1].transAxes, ha="center", fontsize=8)
    colorbar = fig.colorbar(image, ax=axes[1], fraction=0.040, pad=0.025)
    colorbar.set_label("Majority accuracy (%)", fontsize=7.2)
    colorbar.ax.tick_params(labelsize=6.8)
    fig.subplots_adjust(wspace=0.42, bottom=0.22)
    save_figure(fig, output_dir, "figure-3-combined", dpi)


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
    parser.add_argument("--violin-width", type=float, default=5.0)
    parser.add_argument("--violin-height", type=float, default=3.15)
    parser.add_argument("--heatmap-width", type=float, default=6.35)
    parser.add_argument("--heatmap-height", type=float, default=3.65)
    parser.add_argument("--combined-width", type=float, default=10.0)
    parser.add_argument("--combined-height", type=float, default=3.55)
    parser.add_argument(
        "--only",
        nargs="*",
        choices=["latency", "heatmap", "combined"],
        default=None,
    )
    args = parser.parse_args()

    analysis_dir = args.analysis_dir.resolve()
    output_dir = (args.output_dir or analysis_dir.parent / "figures").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        trials, questions, configurations = load_analysis(analysis_dir)
    except (
        FigureInputError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        pd.errors.ParserError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    selected = set(args.only or ["latency", "heatmap", "combined"])
    if "latency" in selected:
        make_latency_violin(
            trials,
            configurations,
            output_dir,
            width=args.violin_width,
            height=args.violin_height,
            dpi=args.dpi,
        )
    if "heatmap" in selected:
        make_accuracy_heatmap(
            trials,
            questions,
            configurations,
            output_dir,
            width=args.heatmap_width,
            height=args.heatmap_height,
            dpi=args.dpi,
        )
    if "combined" in selected:
        make_combined_figure(
            trials,
            questions,
            configurations,
            output_dir,
            width=args.combined_width,
            height=args.combined_height,
            dpi=args.dpi,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
