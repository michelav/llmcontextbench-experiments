#!/usr/bin/env python3
"""Build the combined Table 3 of the SBES 2026 LLMContextBench tool paper."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def latex_rows(frame: pd.DataFrame) -> list[str]:
    rows: list[str] = []
    for record in frame.to_dict(orient="records"):
        rows.append(" & ".join(str(record[column]) for column in frame.columns) + r" \\")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lattes", type=Path, default=Path("experiments/tool-paper/expected/table-3a-lattes.csv"))
    parser.add_argument("--repoqa", type=Path, default=Path("experiments/repoqa/baseline-01/derived/analysis/tool-paper-table-3b.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/tool-paper/generated"))
    args = parser.parse_args()

    for path in (args.lattes, args.repoqa):
        if not path.is_file():
            print(f"ERROR: missing input table: {path}", file=sys.stderr)
            return 2

    lattes = pd.read_csv(args.lattes, dtype=str).fillna("")
    repoqa = pd.read_csv(args.repoqa, dtype=str).fillna("")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    lattes.to_csv(output_dir / "table-3a-lattes.csv", index=False)
    repoqa.to_csv(output_dir / "table-3b-repoqa.csv", index=False)

    markdown = [
        "# Table 3: Effectiveness, token cost, latency, and observed calls",
        "",
        "## (a) Lattes dataset",
        "",
        lattes.to_markdown(index=False),
        "",
        "## (b) RepoQA dataset",
        "",
        repoqa.to_markdown(index=False),
        "",
    ]
    (output_dir / "table-3.md").write_text("\n".join(markdown), encoding="utf-8")

    latex = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Effectiveness, token cost, latency, and observed calls by context provisioning configuration.}",
        r"\label{tab:combined-results}",
        r"\begin{subtable}{\linewidth}",
        r"\centering",
        r"\caption{Lattes dataset.}",
        r"\begin{tabular}{" + "l" + "r" * (len(lattes.columns) - 1) + "}",
        r"\toprule",
        " & ".join(lattes.columns) + r" \\",
        r"\midrule",
        *latex_rows(lattes),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{subtable}",
        r"\vspace{0.5em}",
        r"\begin{subtable}{\linewidth}",
        r"\centering",
        r"\caption{RepoQA dataset.}",
        r"\begin{tabular}{" + "l" + "r" * (len(repoqa.columns) - 1) + "}",
        r"\toprule",
        " & ".join(repoqa.columns) + r" \\",
        r"\midrule",
        *latex_rows(repoqa),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{subtable}",
        r"\end{table}",
        "",
    ]
    (output_dir / "table-3.tex").write_text("\n".join(latex), encoding="utf-8")
    print(f"Wrote combined Table 3 artifacts to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
