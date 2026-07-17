#!/usr/bin/env python3
"""
Regenerate article figures from a COPA baseline experiment.

Generated figures:
  - strategy heatmap:
      <output_dir>/rq3_question_strategy_heatmap_muted.pdf
      <output_dir>/rq3_question_strategy_heatmap_muted.png

  - latency boxplot by strategy:
      <output_dir>/rq2_latency_boxplot_strategy.pdf
      <output_dir>/rq2_latency_boxplot_strategy.png

  - Pareto / trade-off chart:
      <output_dir>/rq2_pareto_latency_improved.pdf
      <output_dir>/rq2_pareto_latency_improved.png

  - question disagreement chart:
      <output_dir>/rq3_question_difficulty_disagreement.pdf
      <output_dir>/rq3_question_difficulty_disagreement.png

Expected input layout:
  experiments/baseline_001/
    answers.jsonl
    judge_votes.jsonl

Usage:
  python scripts/regenerate_article_figures.py experiments/baseline_001 --output-dir figures

Optional:
  python scripts/regenerate_article_figures.py experiments/baseline_001 \
    --output-dir figures \
    --dpi 700 \
    --heatmap-width 6.35 \
    --heatmap-height 3.65
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap


CFG_ORDER = ["I-HTML", "I-JSON", "Func.", "L-MCP", "R-MCP"]

QUESTION_ORDER = [
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


def cfg_label(row: pd.Series) -> str:
    strategy = row.get("strategy")
    fmt = row.get("format")

    if strategy == "inline" and fmt == "html":
        return "I-HTML"
    if strategy == "inline" and fmt == "json":
        return "I-JSON"
    if strategy == "local_function":
        return "Func."
    if strategy == "local_mcp":
        return "L-MCP"
    if strategy == "mcp":
        return "R-MCP"

    return f"{strategy}_{fmt}"


def criterion_rating(criterias: object, criterion: str) -> str | None:
    if isinstance(criterias, dict):
        payload = criterias.get(criterion)
        if isinstance(payload, dict):
            value = payload.get("rating")
            return str(value) if value is not None else None
    return None


def nested_number(payload: object, key: str) -> float:
    if isinstance(payload, dict):
        value = payload.get(key)
        if value is not None:
            return float(value)
    return np.nan


def load_runs(experiment_dir: Path) -> pd.DataFrame:
    answers_path = experiment_dir / "answers.jsonl"
    votes_path = experiment_dir / "judge_votes.jsonl"

    if not answers_path.exists():
        raise FileNotFoundError(f"Missing file: {answers_path}")
    if not votes_path.exists():
        raise FileNotFoundError(f"Missing file: {votes_path}")

    answers = pd.read_json(answers_path, lines=True)
    votes = pd.read_json(votes_path, lines=True)

    answers["Cfg."] = answers.apply(cfg_label, axis=1)

    answers["durationS"] = answers["timing"].apply(
        lambda d: nested_number(d, "durationMs")
    ) / 1000.0

    answers["queryTokens"] = answers["usage"].apply(
        lambda d: nested_number(d, "totalTokens")
    )

    votes["correctness"] = votes["criterias"].apply(
        lambda c: criterion_rating(c, "correctness")
    )
    votes["completeness"] = votes["criterias"].apply(
        lambda c: criterion_rating(c, "completeness")
    )
    votes["both_meet"] = (
        votes["correctness"].eq("meets")
        & votes["completeness"].eq("meets")
    )

    vote_rows = []
    for run_id, group in votes.groupby("runId"):
        correctness = list(group["correctness"].dropna())
        completeness = list(group["completeness"].dropna())
        meet_votes = int(group["both_meet"].sum())

        # Full disagreement: all three labels appear among the three judges
        # for at least one criterion.
        full_disagreement = (
            len(set(correctness)) == 3
            or len(set(completeness)) == 3
        )

        vote_rows.append(
            {
                "runId": run_id,
                "meet_votes": meet_votes,
                "majority_correct": meet_votes >= 2,
                "unanimous_correct": meet_votes == 3,
                "full_disagreement": full_disagreement,
            }
        )

    vote_agg = pd.DataFrame(vote_rows)

    runs = answers.merge(vote_agg, on="runId", how="left")
    return runs


def make_strategy_heatmap(
    runs: pd.DataFrame,
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    matrix = (
        runs.pivot_table(
            index="questionId",
            columns="Cfg.",
            values="majority_correct",
            aggfunc="mean",
        ) * 100
    ).reindex(QUESTION_ORDER)[CFG_ORDER]

    # Muted, print-friendly sequential palette.
    muted_blue = LinearSegmentedColormap.from_list(
        "muted_blue",
        ["#f8f8f8", "#edf3f8", "#d9e8f2", "#b8d3e5", "#82b4d2", "#4f8fbd"],
        N=256,
    )

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    im = ax.imshow(
        matrix.values,
        aspect="auto",
        vmin=0,
        vmax=100,
        interpolation="nearest",
        cmap=muted_blue,
    )

    ax.set_xticks(np.arange(len(CFG_ORDER)))
    ax.set_xticklabels(CFG_ORDER, fontsize=7.8)
    ax.set_yticks(np.arange(len(QUESTION_ORDER)))
    ax.set_yticklabels(QUESTION_ORDER, fontsize=7.2)
    ax.set_title("Majority accuracy by question and strategy", fontsize=9.5)
    ax.set_xlabel("Context provisioning configuration", fontsize=8.3)
    ax.set_ylabel("Question", fontsize=8.3)

    ax.set_xticks(np.arange(-0.5, len(CFG_ORDER), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(QUESTION_ORDER), 1), minor=True)
    ax.grid(which="minor", color="#ffffff", linewidth=0.9)
    ax.tick_params(which="minor", bottom=False, left=False)

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix.iloc[i, j]
            text_color = "#222222" if value < 72 else "#ffffff"
            ax.text(
                j,
                i,
                f"{value:.0f}",
                ha="center",
                va="center",
                fontsize=6.9,
                color=text_color,
            )

    for spine in ax.spines.values():
        spine.set_linewidth(0.6)
        spine.set_color("#666666")

    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Majority accuracy (%)", fontsize=7.5)
    cbar.ax.tick_params(labelsize=7.0)

    fig.tight_layout()

    pdf_path = output_dir / "rq3_question_strategy_heatmap_muted.pdf"
    png_path = output_dir / "rq3_question_strategy_heatmap_muted.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=dpi)
    plt.close(fig)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")


def make_latency_boxplot(
    runs: pd.DataFrame,
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    data = [
        runs.loc[runs["Cfg."] == cfg, "durationS"].dropna().to_numpy()
        for cfg in CFG_ORDER
    ]

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)

    # Matplotlib 3.9+ prefers tick_labels; labels still works on older versions.
    try:
        ax.boxplot(data, tick_labels=CFG_ORDER, showmeans=True)
    except TypeError:
        ax.boxplot(data, labels=CFG_ORDER, showmeans=True)

    ax.set_title("Query latency distribution by strategy", fontsize=9.5)
    ax.set_xlabel("Context provisioning configuration", fontsize=8.5)
    ax.set_ylabel("Query duration (s)", fontsize=8.5)
    ax.tick_params(axis="both", labelsize=7.5)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.55)

    fig.tight_layout()

    pdf_path = output_dir / "rq2_latency_boxplot_strategy.pdf"
    png_path = output_dir / "rq2_latency_boxplot_strategy.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=dpi)
    plt.close(fig)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")


def make_pareto_tradeoff(
    runs: pd.DataFrame,
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    summary = (
        runs.groupby("Cfg.", as_index=False)
        .agg(
            Majority=("majority_correct", "mean"),
            TotalTokens=("queryTokens", "sum"),
            MajorityCount=("majority_correct", "sum"),
            MedianSec=("durationS", "median"),
        )
    )

    summary["MajorityPct"] = summary["Majority"] * 100
    summary["TokPerMajK"] = summary["TotalTokens"] / summary["MajorityCount"] / 1000.0
    summary["LatencyBubble"] = 45 + summary["MedianSec"] * 34

    frontier_rows = []
    for _, row in summary.iterrows():
        dominated = False
        for _, other in summary.iterrows():
            if (
                other["TokPerMajK"] <= row["TokPerMajK"]
                and other["MajorityPct"] >= row["MajorityPct"]
                and (
                    other["TokPerMajK"] < row["TokPerMajK"]
                    or other["MajorityPct"] > row["MajorityPct"]
                )
            ):
                dominated = True
                break
        if not dominated:
            frontier_rows.append(row)

    frontier = pd.DataFrame(frontier_rows).sort_values("TokPerMajK")

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.scatter(
        summary["TokPerMajK"],
        summary["MajorityPct"],
        s=summary["LatencyBubble"],
        alpha=0.85,
    )

    ax.plot(
        frontier["TokPerMajK"],
        frontier["MajorityPct"],
        linestyle="--",
        linewidth=1.2,
        color="#333333",
    )

    annotations = {
        "R-MCP": {"xytext": (45, 38.3), "text": "R-MCP\nlowest cost"},
        "Func.": {"xytext": (66, 34.4), "text": "Func."},
        "L-MCP": {"xytext": (66, 36.0), "text": "L-MCP"},
        "I-JSON": {"xytext": (119, 46.35), "text": "I-JSON\nhighest quality"},
        "I-HTML": {"xytext": (143, 41.2), "text": "I-HTML\ndominated"},
    }

    for _, row in summary.iterrows():
        cfg = row["Cfg."]
        item = annotations.get(cfg, {"xytext": (row["TokPerMajK"], row["MajorityPct"]), "text": cfg})
        ax.annotate(
            item["text"],
            xy=(row["TokPerMajK"], row["MajorityPct"]),
            xytext=item["xytext"],
            fontsize=7.4,
            arrowprops={"arrowstyle": "-", "linewidth": 0.65},
            ha="left",
            va="center",
        )

    ax.annotate(
        "better",
        xy=(23, 46.0),
        xytext=(61, 44.1),
        fontsize=7.5,
        arrowprops={"arrowstyle": "->", "linewidth": 0.75},
        ha="center",
    )
    ax.text(146, 34.45, "bubble area ∝ median latency", fontsize=7.2)
    ax.text(27, 36.62, "Pareto frontier", fontsize=7.2)

    ax.set_xlabel("Query tokens per majority-correct answer (thousands)", fontsize=8.5)
    ax.set_ylabel("Majority accuracy (%)", fontsize=8.5)
    ax.set_title("Accuracy--cost--latency trade-off", fontsize=9.5)
    ax.set_xlim(15, 205)
    ax.set_ylim(33.7, 47.0)
    ax.tick_params(axis="both", labelsize=7.5)
    ax.grid(True, linestyle=":", linewidth=0.55)

    fig.tight_layout()

    pdf_path = output_dir / "rq2_pareto_latency_improved.pdf"
    png_path = output_dir / "rq2_pareto_latency_improved.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=dpi)
    plt.close(fig)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")


def make_question_disagreement(
    runs: pd.DataFrame,
    output_dir: Path,
    *,
    width: float,
    height: float,
    dpi: int,
) -> None:
    q_summary = (
        runs.groupby("questionId", as_index=False)
        .agg(
            Majority=("majority_correct", "mean"),
            Unanimous=("unanimous_correct", "mean"),
            FullDis=("full_disagreement", "mean"),
        )
    )

    q_summary["MajorityPct"] = q_summary["Majority"] * 100
    q_summary["UnanimousPct"] = q_summary["Unanimous"] * 100
    q_summary["FullDisPct"] = q_summary["FullDis"] * 100
    q_summary = q_summary.set_index("questionId").reindex(QUESTION_ORDER).reset_index()

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)

    y = np.arange(len(q_summary))
    ax.scatter(q_summary["MajorityPct"], y, s=38, label="Majority")
    ax.scatter(q_summary["UnanimousPct"], y, s=38, marker="s", label="Unanimous")
    ax.scatter(q_summary["FullDisPct"], y, s=38, marker="^", label="Full disagreement")

    ax.set_yticks(y)
    ax.set_yticklabels(q_summary["questionId"], fontsize=7.2)
    ax.invert_yaxis()
    ax.set_xlabel("Runs (%)", fontsize=8.5)
    ax.set_title("Question difficulty and judge disagreement", fontsize=9.5)
    ax.tick_params(axis="x", labelsize=7.5)
    ax.grid(True, axis="x", linestyle=":", linewidth=0.55)
    ax.legend(fontsize=7.3, loc="lower right")

    fig.tight_layout()

    pdf_path = output_dir / "rq3_question_difficulty_disagreement.pdf"
    png_path = output_dir / "rq3_question_difficulty_disagreement.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=dpi)
    plt.close(fig)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "experiment_dir",
        type=Path,
        help="Path to the baseline experiment directory, e.g., experiments/baseline_001",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("figures"),
        help="Directory where figures will be written.",
    )
    parser.add_argument("--dpi", type=int, default=700)

    parser.add_argument("--heatmap-width", type=float, default=6.35)
    parser.add_argument("--heatmap-height", type=float, default=3.65)

    parser.add_argument("--boxplot-width", type=float, default=5.0)
    parser.add_argument("--boxplot-height", type=float, default=3.0)

    parser.add_argument("--pareto-width", type=float, default=5.15)
    parser.add_argument("--pareto-height", type=float, default=3.15)

    parser.add_argument("--disagreement-width", type=float, default=5.0)
    parser.add_argument("--disagreement-height", type=float, default=3.2)

    parser.add_argument(
        "--only",
        nargs="*",
        choices=["heatmap", "latency", "pareto", "disagreement"],
        default=None,
        help="Generate only selected figures. Default: generate all.",
    )

    args = parser.parse_args()

    experiment_dir = args.experiment_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = set(args.only or ["heatmap", "latency", "pareto", "disagreement"])

    runs = load_runs(experiment_dir)

    if "heatmap" in selected:
        make_strategy_heatmap(
            runs,
            output_dir,
            width=args.heatmap_width,
            height=args.heatmap_height,
            dpi=args.dpi,
        )

    if "latency" in selected:
        make_latency_boxplot(
            runs,
            output_dir,
            width=args.boxplot_width,
            height=args.boxplot_height,
            dpi=args.dpi,
        )

    if "pareto" in selected:
        make_pareto_tradeoff(
            runs,
            output_dir,
            width=args.pareto_width,
            height=args.pareto_height,
            dpi=args.dpi,
        )

    if "disagreement" in selected:
        make_question_disagreement(
            runs,
            output_dir,
            width=args.disagreement_width,
            height=args.disagreement_height,
            dpi=args.dpi,
        )


if __name__ == "__main__":
    main()
