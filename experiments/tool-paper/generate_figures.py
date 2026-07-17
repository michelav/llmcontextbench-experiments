#!/usr/bin/env python3
"""Generate reproducible redrawings of the conceptual figures in the tool paper."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


def box(ax, xy, width, height, text, *, fontsize=8, linewidth=1.0):
    patch = FancyBboxPatch(xy, width, height, boxstyle="round,pad=0.02", fill=False, linewidth=linewidth)
    ax.add_patch(patch)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text, ha="center", va="center", fontsize=fontsize)
    return patch


def arrow(ax, start, end, *, dashed=False):
    patch = FancyArrowPatch(start, end, arrowstyle="->", mutation_scale=10, linewidth=0.9, linestyle="--" if dashed else "-")
    ax.add_patch(patch)


def save(fig, output_dir: Path, stem: str, dpi: int):
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("pdf", "png", "svg"):
        kwargs = {"bbox_inches": "tight"}
        if suffix == "png":
            kwargs["dpi"] = dpi
        path = output_dir / f"{stem}.{suffix}"
        fig.savefig(path, **kwargs)
        print(f"Wrote {path}")
    plt.close(fig)


def domain_model(output_dir: Path, dpi: int):
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    box(ax, (0.4, 4.6), 1.7, 0.7, "Experiment")
    box(ax, (3.0, 4.6), 1.5, 0.7, "Dataset")
    box(ax, (5.3, 4.6), 1.5, 0.7, "Model")
    box(ax, (7.6, 4.6), 1.8, 0.7, "Strategy")
    box(ax, (2.2, 2.9), 1.4, 0.7, "Instance")
    box(ax, (4.3, 2.9), 1.4, 0.7, "Task")
    box(ax, (6.4, 2.9), 1.4, 0.7, "Trial")
    box(ax, (4.0, 1.2), 1.6, 0.7, "Response")
    box(ax, (6.4, 1.2), 1.6, 0.7, "Evaluation")
    box(ax, (8.6, 1.2), 1.0, 0.7, "Trace")

    arrow(ax, (2.1, 4.95), (3.0, 4.95))
    arrow(ax, (2.0, 4.65), (2.7, 3.6))
    arrow(ax, (2.0, 4.8), (4.6, 3.6))
    arrow(ax, (4.5, 4.8), (6.65, 3.6))
    arrow(ax, (6.05, 4.6), (6.85, 3.6))
    arrow(ax, (8.1, 4.6), (7.25, 3.6))
    arrow(ax, (3.6, 3.25), (6.4, 3.25))
    arrow(ax, (5.7, 3.25), (6.4, 3.25))
    arrow(ax, (6.75, 2.9), (5.2, 1.9))
    arrow(ax, (5.6, 1.55), (6.4, 1.55))
    arrow(ax, (7.8, 1.55), (8.6, 1.55), dashed=True)
    arrow(ax, (7.2, 2.9), (9.0, 1.9), dashed=True)

    ax.set_title("Conceptual domain model of LLMContextBench", fontsize=11)
    ax.text(0.5, 0.35, "A trial binds one dataset instance, task, model, strategy, format, and repetition.\nExecution produces a response; evaluation and tracing preserve assessment and observability artifacts.", fontsize=8)
    fig.tight_layout()
    save(fig, output_dir, "figure-1-domain-model", dpi)


def workflow(output_dir: Path, dpi: int):
    fig, ax = plt.subplots(figsize=(10.0, 4.4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6)
    ax.axis("off")

    phases = [
        (0.3, "Dataset\nfetch", "dataset package"),
        (2.5, "Plan", "manifest.json\ntrials.jsonl"),
        (4.9, "Execute", "responses.jsonl\nexecution traces"),
        (7.3, "Evaluate", "evals.jsonl / scores\nevaluation traces"),
        (9.7, "Export &\nanalyze", "results.csv\ntables & figures"),
    ]
    for x, title, artifact in phases:
        box(ax, (x, 3.4), 1.7, 1.0, title, fontsize=9)
        box(ax, (x, 1.2), 1.7, 1.0, artifact, fontsize=7.5)
        arrow(ax, (x + 0.85, 3.4), (x + 0.85, 2.2))
    for left, right in zip(phases, phases[1:]):
        arrow(ax, (left[0] + 1.7, 3.9), (right[0], 3.9))

    ax.text(0.35, 5.15, "Experiment configuration", fontsize=8)
    arrow(ax, (1.7, 5.05), (2.8, 4.4))
    ax.text(7.25, 5.15, "Dataset evidence / oracle", fontsize=8)
    arrow(ax, (8.15, 5.0), (8.15, 4.4))
    ax.text(0.35, 0.35, "Each phase consumes explicit artifacts and can be inspected, resumed, filtered, or re-executed independently.", fontsize=8)
    ax.set_title("LLMContextBench artifact-oriented workflow", fontsize=11)
    fig.tight_layout()
    save(fig, output_dir, "figure-2-workflow", dpi)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/tool-paper/generated/figures"))
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--only", nargs="*", choices=["domain-model", "workflow"], default=None)
    args = parser.parse_args()
    selected = set(args.only or ["domain-model", "workflow"])
    if "domain-model" in selected:
        domain_model(args.output_dir, args.dpi)
    if "workflow" in selected:
        workflow(args.output_dir, args.dpi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
