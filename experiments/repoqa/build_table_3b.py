#!/usr/bin/env python3
"""Generate RepoQA Table 3(b) from baseline-derived CSV files.

The script never reads raw JSONL artifacts. It consumes ``repoqa_trials.csv``
created by ``derive_repoqa.py`` and applies an explicit immutable selection
manifest. Expected paper values are optional verification fixtures only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from analyze_repoqa import (
    ArtifactError,
    format_k,
    require_complete_analysis,
    summarize,
    verify,
)

REQUIRED_CONFIGS = ["I-Code", "I-JSON", "Func.", "L-MCP"]
TABLE_COLUMNS = ["Config", "N", "Hit", "Pass", "Sim.", "Tok./T", "Tok./P", "Sec.", "Calls"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_nullable_bool(series: pd.Series, column: str) -> pd.Series:
    normalized = series.astype("string").str.strip().str.lower()
    missing = normalized.isna() | normalized.isin({"", "nan", "none", "<na>"})
    valid = missing | normalized.isin({"true", "false", "1", "0"})
    if not valid.all():
        values = sorted(normalized.loc[~valid].dropna().unique())
        raise ArtifactError(f"Invalid boolean values in {column}: {values}")
    result = pd.Series(pd.NA, index=series.index, dtype="boolean")
    result.loc[normalized.isin({"true", "1"})] = True
    result.loc[normalized.isin({"false", "0"})] = False
    return result


def load_trials(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise ArtifactError(f"Missing derived trial CSV: {path}")
    frame = pd.read_csv(path)
    required = {
        "trial_id",
        "configuration",
        "hit",
        "passed",
        "similarity",
        "total_tokens",
        "duration_sec",
        "calls",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ArtifactError(f"{path} is missing columns: {', '.join(missing)}")
    if frame["trial_id"].duplicated().any():
        raise ArtifactError("repoqa_trials.csv contains duplicate trial_id values")

    frame["hit"] = parse_nullable_bool(frame["hit"], "hit")
    frame["passed"] = parse_nullable_bool(frame["passed"], "passed")
    if "analysis_complete" in frame.columns:
        frame["analysis_complete"] = parse_nullable_bool(
            frame["analysis_complete"], "analysis_complete"
        ).fillna(False)
    else:
        frame["analysis_complete"] = ~frame[
            ["hit", "passed", "similarity", "total_tokens", "duration_sec", "calls"]
        ].isna().any(axis=1)

    for column in ("similarity", "total_tokens", "duration_sec", "calls"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["trial_id"] = frame["trial_id"].astype(str)
    frame["configuration"] = frame["configuration"].astype(str)
    return frame


def load_selection(path: Path) -> tuple[dict[str, Any], list[str], int]:
    if not path.is_file():
        raise ArtifactError(
            f"Missing paper selection: {path}. Copy paper-selection.example.json "
            "and record the exact Table 3(b) trial IDs."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ArtifactError("Paper selection must be a JSON object")
    trial_ids = payload.get("trialIds")
    if not isinstance(trial_ids, list) or not trial_ids:
        raise ArtifactError(
            "paper-selection.json must contain a non-empty trialIds array; "
            "implicit filters are not sufficient for exact paper reproduction"
        )
    ids = [str(value) for value in trial_ids]
    if len(ids) != len(set(ids)):
        raise ArtifactError("paper-selection.json contains duplicate trial IDs")
    expected_per_config = int(payload.get("expectedPerConfiguration", 45))
    return payload, ids, expected_per_config


def select_trials(frame: pd.DataFrame, trial_ids: list[str], expected_per_config: int) -> pd.DataFrame:
    by_id = frame.set_index("trial_id", drop=False)
    missing = [trial_id for trial_id in trial_ids if trial_id not in by_id.index]
    if missing:
        raise ArtifactError(
            f"Selection references {len(missing)} absent trial IDs; first: {', '.join(missing[:5])}"
        )
    selected = by_id.loc[trial_ids].reset_index(drop=True)
    present = set(selected["configuration"])
    if present != set(REQUIRED_CONFIGS):
        raise ArtifactError(
            f"Expected configurations {REQUIRED_CONFIGS}, found {sorted(present)}"
        )
    counts = selected.groupby("configuration").size().to_dict()
    invalid = {
        config: int(counts.get(config, 0))
        for config in REQUIRED_CONFIGS
        if int(counts.get(config, 0)) != expected_per_config
    }
    if invalid:
        rendered = ", ".join(f"{key}={value}" for key, value in invalid.items())
        raise ArtifactError(
            f"Expected {expected_per_config} trials per configuration, found {rendered}"
        )
    require_complete_analysis(selected, context="Table 3(b) selection")
    return selected


def paper_table(summary: pd.DataFrame) -> pd.DataFrame:
    table = summary[TABLE_COLUMNS].copy()
    table["N"] = table["N"].astype(int)
    table["Hit"] = table["Hit"].map(lambda value: f"{value:.1f}")
    table["Pass"] = table["Pass"].map(lambda value: f"{value:.1f}")
    table["Sim."] = table["Sim."].map(lambda value: f"{value:.2f}")
    table["Tok./T"] = table["Tok./T"].map(lambda value: format_k(float(value)))
    table["Tok./P"] = table["Tok./P"].map(lambda value: format_k(float(value)))
    table["Sec."] = table["Sec."].map(lambda value: f"{value:.2f}")
    table["Calls"] = table["Calls"].map(lambda value: f"{value:.2f}")
    return table


def write_latex(table: pd.DataFrame, path: Path) -> None:
    lines = [
        r"\begin{tabular}{lrrrrrrrr}",
        r"\toprule",
        r"Config. & N & Hit & Pass & Sim. & Tok./T & Tok./P & Sec. & Calls \\",
        r"\midrule",
    ]
    for row in table.to_dict(orient="records"):
        lines.append(" & ".join(str(row[column]) for column in table.columns) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "analysis_dir",
        type=Path,
        nargs="?",
        default=Path("experiments/repoqa/baseline-01/derived/analysis"),
    )
    parser.add_argument(
        "--selection",
        type=Path,
        required=True,
        help="Immutable JSON manifest containing the exact Table 3(b) trial IDs.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--expected", type=Path, default=None)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    analysis_dir = args.analysis_dir.resolve()
    trials_path = analysis_dir / "repoqa_trials.csv"
    output_dir = (args.output_dir or analysis_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        frame = load_trials(trials_path)
        selection, trial_ids, expected_per_config = load_selection(args.selection.resolve())
        selected = select_trials(frame, trial_ids, expected_per_config)
        summary = summarize(selected)
        table = paper_table(summary)
        table.to_csv(output_dir / "table-3b.csv", index=False)
        write_latex(table, output_dir / "table-3b.tex")
        selected.sort_values(["configuration", "trial_id"]).to_csv(
            output_dir / "table-3b-selected-trials.csv", index=False
        )
        manifest = {
            "schemaVersion": "1.1",
            "inputTrials": str(trials_path),
            "inputTrialsSha256": sha256_file(trials_path),
            "selection": str(args.selection.resolve()),
            "selectionSha256": sha256_file(args.selection.resolve()),
            "selectedTrials": int(len(selected)),
            "expectedPerConfiguration": expected_per_config,
            "configurations": {
                str(key): int(value)
                for key, value in selected.groupby("configuration").size().items()
            },
            "completeSelectedTrials": int(selected["analysis_complete"].fillna(False).sum()),
            "expectedFilesUsedAsInputs": False,
            "selectionDescription": selection.get("description"),
        }
        (output_dir / "table-3b-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except (ArtifactError, OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(table.to_string(index=False))
    print(f"Wrote RepoQA Table 3(b) to {output_dir}")

    if args.expected:
        errors = verify(summary, args.expected.resolve())
        if errors:
            print("Table 3(b) verification failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1 if args.verify else 0
        print("Table 3(b) verification passed.")
    elif args.verify:
        print("ERROR: --verify requires --expected", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
