# Tool-Paper Reproduction

This directory coordinates the artifacts reported in:

- **LLMContextBench: A Benchmark Tool for Evaluating Context Provisioning Strategies in LLM-Based Systems**.

The paper uses two experimental datasets:

- Lattes, evaluated through three LLM judges;
- RepoQA, evaluated through the deterministic RepoQA scorer.

## Reproduced paper elements

| Paper element | Source | Command | Output |
|---|---|---|---|
| Figure 1: conceptual domain model | code-generated diagram | `make tool-paper-figures` | `generated/figures/figure-1-domain-model.*` |
| Figure 2: workflow | code-generated diagram | `make tool-paper-figures` | `generated/figures/figure-2-workflow.*` |
| Table 3(a): Lattes | preserved/published Lattes summary | `make tool-paper-table` | `generated/table-3a-lattes.csv` |
| Table 3(b): RepoQA | `responses.jsonl` + `evals.jsonl` | `make tool-paper-table REPOQA_SELECTION=...` | `generated/table-3b-repoqa.csv` |
| Combined Table 3 | both summaries | `make tool-paper-table REPOQA_SELECTION=...` | `generated/table-3.md` and `generated/table-3.tex` |
| Supporting RepoQA diagnostics | RepoQA response/evaluation artifacts | `make repoqa-figures REPOQA_SELECTION=...` | `../repoqa/baseline-01/derived/figures/` |

The conceptual figures are reproducible redrawings from the architecture and workflow described in the paper. If the exact editable sources used to render the camera-ready figures are available, they should also be preserved in this directory before the final DOI release.

## Environment

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-analysis.txt
```

The offline environment requires only pandas, NumPy, Matplotlib, and tabulate. It performs no provider calls.

## Complete-baseline analysis

To inspect all committed RepoQA outputs:

```bash
make repoqa-analysis
make repoqa-figures
```

This is useful for diagnostics but does not by itself reproduce the `N = 45` per configuration reported in Table 3(b).

## Exact tool-paper reproduction

Create and populate:

```text
experiments/repoqa/paper-selection.json
```

using the exact immutable trial IDs selected for the paper. The example file is:

```text
experiments/repoqa/paper-selection.example.json
```

Then run:

```bash
make reproduce-tool-paper \
  REPOQA_SELECTION=experiments/repoqa/paper-selection.json
```

When a selection is supplied, the Makefile asks the analysis script to compare the calculated RepoQA summary against:

```text
experiments/repoqa/expected/tool-paper-table-3b.csv
```

The process fails when the selected outputs do not reproduce the published table within the documented tolerances.

## Generated artifacts

```text
experiments/tool-paper/generated/
├── table-3a-lattes.csv
├── table-3b-repoqa.csv
├── table-3.md
├── table-3.tex
└── figures/
    ├── figure-1-domain-model.pdf
    ├── figure-1-domain-model.png
    ├── figure-1-domain-model.svg
    ├── figure-2-workflow.pdf
    ├── figure-2-workflow.png
    └── figure-2-workflow.svg
```

RepoQA-specific diagnostic tables and figures are written below:

```text
experiments/repoqa/baseline-01/derived/
```

## Interpretation of Table 3(b)

- `Hit` means that the best function matched by the deterministic scorer is the requested target.
- `Pass` means that the selected response satisfies the RepoQA scorer and threshold policy.
- `Sim.` is the mean best similarity score.
- `Tok./T` is query-phase token cost per selected trial.
- `Tok./P` is total query-phase token cost divided by passing trials.
- `Sec.` is median generation duration.
- `Calls` is mean observed operation-call count.

Do not include LLM-judge cost in RepoQA metrics because this dataset uses deterministic scoring.
