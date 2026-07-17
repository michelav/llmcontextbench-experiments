#!/usr/bin/env python3
"""Generate diagnostic RepoQA figures from preserved CTXBench outputs."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analyze_repoqa import ArtifactError, apply_selection, load_trials, summarize

CONFIG_ORDER = ["I-Code", "I-JSON", "Func.", "L-MCP"]


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


def ordered(summary: pd.DataFrame) -> pd.DataFrame:
    return summary.set_index("Config").reindex([item for item in CONFIG_ORDER if item in set(summary["Config"])])


def rates(summary: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    data = ordered(summary)
    x = np.arange(len(data))
    width = 0.36
    fig, ax = plt.subplots(figsize=(5.4, 3.1))
    ax.bar(x - width / 2, data["Hit"], width, label="Hit")
    ax.bar(x + width / 2, data["Pass"], width, label="Pass")
    ax.set_xticks(x, data.index)
    ax.set_ylabel("Rate (%)")
    ax.set_xlabel("Context provisioning configuration")
    ax.set_ylim(0, 105)
    ax.legend()
    ax.grid(axis="y", linestyle=":", linewidth=0.6)
    fig.tight_layout()
    save_figure(fig, output_dir, "repoqa_hit_pass_rates", dpi)


def tradeoff(summary: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    data = ordered(summary)
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    sizes = 65 + data["Sec."].to_numpy() * 25
    ax.scatter(data["Tok./T"] / 1000.0, data["Pass"], s=sizes, alpha=0.8)
    for label, row in data.iterrows():
        ax.annotate(label, (row["Tok./T"] / 1000.0, row["Pass"]), xytext=(5, 5), textcoords="offset points")
    ax.set_xlabel("Mean query tokens per trial (thousands)")
    ax.set_ylabel("Pass rate (%)")
    ax.set_ylim(min(80, float(data["Pass"].min()) - 3), 103)
    ax.grid(linestyle=":", linewidth=0.6)
    ax.text(0.99, 0.02, "bubble area ∝ median latency", transform=ax.transAxes, ha="right", va="bottom", fontsize=8)
    fig.tight_layout()
    save_figure(fig, output_dir, "repoqa_quality_token_tradeoff", dpi)


def grouped_rate(frame: pd.DataFrame, dimension: str, xlabel: str, stem: str, output_dir: Path, dpi: int) -> None:
    pivot = frame.pivot_table(index=dimension, columns="configuration", values="passed", aggfunc="mean") * 100
    pivot = pivot.reindex(columns=[item for item in CONFIG_ORDER if item in pivot.columns])
    fig, ax = plt.subplots(figsize=(6.0, 3.3))
    pivot.plot(kind="bar", ax=ax)
    ax.set_ylabel("Pass rate (%)")
    ax.set_xlabel(xlabel)
    ax.set_ylim(0, 105)
    ax.legend(title="Configuration", ncol=2)
    ax.grid(axis="y", linestyle=":", linewidth=0.6)
    fig.tight_layout()
    save_figure(fig, output_dir, stem, dpi)


def latency(frame: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    data = [frame.loc[frame["configuration"] == config, "duration_sec"].dropna().to_numpy() for config in CONFIG_ORDER if config in set(frame["configuration"])]
    labels = [config for config in CONFIG_ORDER if config in set(frame["configuration"])]
    fig, ax = plt.subplots(figsize=(5.2, 3.1))
    try:
        ax.boxplot(data, tick_labels=labels, showmeans=True)
    except TypeError:
        ax.boxplot(data, labels=labels, showmeans=True)
    ax.set_ylabel("Query duration (s)")
    ax.set_xlabel("Context provisioning configuration")
    ax.grid(axis="y", linestyle=":", linewidth=0.6)
    fig.tight_layout()
    save_figure(fig, output_dir, "repoqa_latency_distribution", dpi)


def similarity_heatmap(frame: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    pivot = frame.pivot_table(index="language", columns="configuration", values="similarity", aggfunc="mean")
    pivot = pivot.reindex(columns=[item for item in CONFIG_ORDER if item in pivot.columns])
    fig, ax = plt.subplots(figsize=(5.4, 2.8))
    image = ax.imshow(pivot.values, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(np.arange(len(pivot.columns)), pivot.columns)
    ax.set_yticks(np.arange(len(pivot.index)), pivot.index)
    ax.set_xlabel("Context provisioning configuration")
    ax.set_ylabel("Language")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            value = pivot.iloc[i, j]
            if not math.isnan(value):
                ax.text(j, i, f"{value:.2f}", ha="center", va="center")
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("Mean similarity")
    fig.tight_layout()
    save_figure(fig, output_dir, "repoqa_similarity_heatmap", dpi)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_dir", type=Path, nargs="?", default=Path("experiments/repoqa/baseline-01"))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--selection", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--only", nargs="*", choices=["rates", "tradeoff", "context", "language", "latency", "similarity"], default=None)
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    output_dir = (args.output_dir or experiment_dir / "derived" / "figures").resolve()
    try:
        frame = load_trials(experiment_dir)
        frame, _ = apply_selection(frame, args.selection.resolve() if args.selection else None)
        summary = summarize(frame)
    except (ArtifactError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    selected = set(args.only or ["rates", "tradeoff", "context", "language", "latency", "similarity"])
    if "rates" in selected:
        rates(summary, output_dir, args.dpi)
    if "tradeoff" in selected:
        tradeoff(summary, output_dir, args.dpi)
    if "context" in selected:
        grouped_rate(frame, "context_size_k", "Context size (k tokens)", "repoqa_pass_rate_by_context_size", output_dir, args.dpi)
    if "language" in selected:
        grouped_rate(frame, "language", "Programming language", "repoqa_pass_rate_by_language", output_dir, args.dpi)
    if "latency" in selected:
        latency(frame, output_dir, args.dpi)
    if "similarity" in selected:
        similarity_heatmap(frame, output_dir, args.dpi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
