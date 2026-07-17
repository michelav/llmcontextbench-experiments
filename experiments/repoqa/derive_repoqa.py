#!/usr/bin/env python3
"""Generate analysis-ready RepoQA CSV files from the preserved baseline.

This is the official processing stage for RepoQA. It reads the committed
responses and deterministic evaluations through ``analyze_repoqa.py`` and
writes normalized CSV files. Incomplete historical rows are preserved and
explicitly reported instead of being silently discarded or guessed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from analyze_repoqa import ArtifactError, load_trials, summarize, summarize_dimension


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def response_path(experiment_dir: Path) -> Path:
    for name in ("responses.jsonl", "answers.jsonl"):
        candidate = experiment_dir / name
        if candidate.is_file():
            return candidate
    raise ArtifactError(f"No responses.jsonl or answers.jsonl in {experiment_dir}")


def write_outputs(frame: pd.DataFrame, output_dir: Path, experiment_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(frame)

    frame.sort_values(
        ["configuration", "language", "context_size_k", "model_id", "instance_id", "trial_id"]
    ).to_csv(output_dir / "repoqa_trials.csv", index=False)
    summary.to_csv(output_dir / "repoqa_summary_by_configuration.csv", index=False)
    summarize_dimension(frame, "model").to_csv(
        output_dir / "repoqa_summary_by_model.csv", index=False
    )
    summarize_dimension(frame, "language").to_csv(
        output_dir / "repoqa_summary_by_language.csv", index=False
    )
    summarize_dimension(frame, "context_size_k").to_csv(
        output_dir / "repoqa_summary_by_context_size.csv", index=False
    )

    frame[frame["passed"].eq(False) | frame["hit"].eq(False)].to_csv(
        output_dir / "repoqa_failures.csv", index=False
    )
    incomplete = frame.loc[~frame["analysis_complete"].fillna(False).astype(bool)].copy()
    incomplete.to_csv(output_dir / "repoqa_incomplete_trials.csv", index=False)

    responses = response_path(experiment_dir)
    evaluations = experiment_dir / "evals.jsonl"
    manifest = {
        "schemaVersion": "1.1",
        "sourceDirectory": str(experiment_dir),
        "sourceArtifacts": {
            responses.name: {"sha256": sha256_file(responses)},
            evaluations.name: {"sha256": sha256_file(evaluations)},
        },
        "joinedTrials": int(len(frame)),
        "completeTrials": int(frame["analysis_complete"].fillna(False).sum()),
        "incompleteTrials": int(len(incomplete)),
        "incompleteByReason": {
            str(key): int(value)
            for key, value in (
                incomplete.assign(reason=incomplete["incomplete_reasons"].fillna("").str.split(";"))
                .explode("reason")
                .loc[lambda data: data["reason"].ne("")]
                .groupby("reason")
                .size()
                .items()
            )
        },
        "configurations": {
            str(key): int(value) for key, value in frame.groupby("configuration").size().items()
        },
        "models": sorted(str(value) for value in frame["model"].dropna().unique()),
        "languages": sorted(str(value) for value in frame["language"].dropna().unique()),
        "contextSizesK": sorted(
            int(value) for value in frame["context_size_k"].dropna().unique()
        ),
        "note": (
            "Summaries use rows with complete metric sets and report both N and CompleteN. "
            "Incomplete rows remain in repoqa_trials.csv and are listed separately. "
            "No article-value fixture is read or validated."
        ),
    }
    (output_dir / "repoqa_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "experiment_dir",
        type=Path,
        nargs="?",
        default=Path("experiments/repoqa/baseline-01"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any historical response lacks a complete analysis metric set.",
    )
    args = parser.parse_args()

    experiment_dir = args.experiment_dir.resolve()
    output_dir = (args.output_dir or experiment_dir / "derived" / "analysis").resolve()
    try:
        frame = load_trials(experiment_dir, strict=args.strict)
        write_outputs(frame, output_dir, experiment_dir)
    except (ArtifactError, OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    complete = int(frame["analysis_complete"].fillna(False).sum())
    incomplete = int(len(frame) - complete)
    print(f"Wrote RepoQA analysis CSVs to {output_dir}")
    print(f"Trials: {len(frame)} total, {complete} complete, {incomplete} incomplete")
    if incomplete:
        print(
            "See repoqa_incomplete_trials.csv and repoqa_analysis_manifest.json for details."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
