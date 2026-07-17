# RepoQA experiment

This directory contains the preserved RepoQA experiment used in the SBES 2026 Tools Track paper **LLMContextBench: A Benchmark Tool for Evaluating Context Provisioning Strategies in LLM-Based Systems**.

RepoQA evaluates long-context source-code retrieval. Given a natural-language description of a target function and repository-level code context, the model must reproduce the target function. Evaluation is deterministic: the RepoQA scorer records retrieval hit, pass/fail, and code similarity rather than using LLM judges.

## Reproducibility design

The official processing path mirrors the Lattes workflow and separates baseline analysis from paper-table construction:

```text
baseline-01/{responses.jsonl,evals.jsonl}
                     |
                     v
              derive_repoqa.py
                     |
                     v
baseline-01/derived/analysis/repoqa_trials.csv
                     |
                     | + paper-selection.json
                     v
             build_table_3b.py
                     |
                     v
baseline-01/derived/analysis/table-3b.csv
```

`derive_repoqa.py` is the baseline preprocessing stage. It reads the preserved responses and deterministic evaluations and writes normalized CSV files plus a manifest. It never reads published values or a paper-selection file.

`build_table_3b.py` is the presentation stage. It reads only `repoqa_trials.csv`, applies an explicit immutable list of trial IDs, calculates the Table 3(b) metrics, and writes the paper table and a selection/provenance manifest.

Expected values are verification fixtures only. They are never used to choose trials, fill missing data, or compute metrics.

## Important limitation: the paper subset

The committed baseline currently contains **960 responses and 960 evaluations**, while Table 3(b) reports **45 trials for each of four configurations**, for a total of 180 trials. The exact immutable 180-trial subset used for the paper has not yet been recorded in the repository.

Consequently:

- the complete baseline can already be analyzed reproducibly;
- exact Table 3(b) reproduction requires `paper-selection.json` containing the 180 exact trial IDs;
- scripts intentionally reject implicit filtering when generating the paper table;
- the expected CSV is not a substitute for the missing selection.

## Experiment scope

The preserved outputs cover:

- Python, Java, TypeScript, and Rust;
- 4k, 8k, and 16k context sizes;
- four OpenAI and Google generation models;
- inline code (`I-Code`);
- inline JSON (`I-JSON`);
- local function calling (`Func.`);
- local MCP (`L-MCP`).

## Table 3(b) metrics

| Metric | Definition |
|---|---|
| `N` | Number of explicitly selected trials for the configuration. |
| `Hit` | Percentage with `details.repoqa.isBestMatch = true`. |
| `Pass` | Percentage with `details.repoqa.passed = true`. |
| `Sim.` | Mean `details.repoqa.bestSimilarScore`. |
| `Tok./T` | Query-phase tokens divided by all selected trials. |
| `Tok./P` | Query-phase tokens divided by passing selected trials. |
| `Sec.` | Median query duration in seconds. |
| `Calls` | Mean compact operation/tool-call count recorded with responses. |

These definitions and the published aggregate values follow Table 3(b) of the accepted tool-track manuscript.

## Directory layout

```text
experiments/repoqa/
├── README.md
├── experiment.repoqa.json
├── analyze_repoqa.py
├── derive_repoqa.py
├── build_table_3b.py
├── generate_figures.py
├── paper-selection.example.json
├── expected/
│   └── tool-paper-table-3b.csv      # legacy fixture location
└── baseline-01/
    ├── provenance.json
    ├── manifest.json
    ├── trials.jsonl
    ├── responses.jsonl
    ├── evals.jsonl
    ├── evals-summary.json
    └── traces/
```

The repository-level verification fixture is:

```text
expected/table-3b-repoqa.csv
```

`analyze_repoqa.py` remains available as a lower-level compatibility/helper module. The official reproducibility entry points are `derive_repoqa.py` and `build_table_3b.py`.

## Requirements

Offline processing requires Python 3.11 or 3.12 with pandas. The repository-level environment also includes NumPy and Matplotlib for the other analyses and figures.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-analysis.txt
```

Offline analysis does not call model providers or MCP services.

## Analyze the complete committed baseline

From the repository root:

```bash
just repoqa-analyze
```

Equivalent direct command:

```bash
python experiments/repoqa/derive_repoqa.py \
  experiments/repoqa/baseline-01 \
  --output-dir experiments/repoqa/baseline-01/derived/analysis
```

Generated files include:

```text
repoqa_trials.csv
repoqa_summary_by_configuration.csv
repoqa_summary_by_model.csv
repoqa_summary_by_language.csv
repoqa_summary_by_context_size.csv
repoqa_failures.csv
repoqa_analysis_manifest.json
```

The manifest records SHA-256 hashes for `responses.jsonl` and `evals.jsonl`. No Table 3(b) file is created at this stage.

## Record the immutable paper selection

Create the working selection file:

```bash
cp experiments/repoqa/paper-selection.example.json \
  experiments/repoqa/paper-selection.json
```

Populate `trialIds` with the exact 180 trial IDs used in the paper. The generator requires exactly 45 selected trials for each configuration:

```text
I-Code
I-JSON
Func.
L-MCP
```

Do not infer the paper population from row order, timestamps, expected values, or a convenient filter. Use the historically correct trial identifiers.

## Generate Table 3(b)

After recording the selection:

```bash
just repoqa-table
```

To use a selection stored elsewhere:

```bash
REPOQA_SELECTION=/path/to/paper-selection.json just repoqa-table
```

Equivalent direct command:

```bash
python experiments/repoqa/build_table_3b.py \
  experiments/repoqa/baseline-01/derived/analysis \
  --selection experiments/repoqa/paper-selection.json \
  --output-dir experiments/repoqa/baseline-01/derived/analysis
```

Generated artifacts:

```text
table-3b.csv
table-3b.tex
table-3b-selected-trials.csv
table-3b-manifest.json
```

The manifest records the SHA-256 hashes of both `repoqa_trials.csv` and the selection file, the selected counts, and that expected values were not used as inputs.

## Verify against the published table

```bash
just repoqa-verify
```

Equivalent direct command:

```bash
python experiments/repoqa/build_table_3b.py \
  experiments/repoqa/baseline-01/derived/analysis \
  --selection experiments/repoqa/paper-selection.json \
  --output-dir experiments/repoqa/baseline-01/derived/analysis \
  --expected expected/table-3b-repoqa.csv \
  --verify
```

A mismatch returns a non-zero status. Verification occurs only after all metrics have been calculated from the explicitly selected derived rows.

## Clean generated outputs

```bash
just repoqa-clean
```

## Remaining archival blocker

Before assigning a persistent artifact release or claiming exact Table 3(b) reproduction, identify and commit the correct paper selection. The current repository cannot honestly derive that historical subset from the published aggregate values alone.
