# Lattes experiment

This directory contains the preserved Lattes baseline used by the SBES 2026 research-track and tools-track papers associated with LLMContextBench.

The experiment compares five context-provisioning configurations:

- inline HTML (`I-HTML`);
- inline JSON (`I-JSON`);
- local function calling (`Func.`);
- local MCP (`L-MCP`);
- remote MCP (`R-MCP`).

The preserved execution contains 1,200 generated answers and 3,600 individual judge votes. These committed artifacts are the source of truth for all derived numerical results.

**Data note:** the questions are answered against curricula publicly accessible on the Brazilian Lattes Platform, each identified by its public numeric Lattes ID. No information beyond what each researcher already publishes on their own public CV page is collected, generated, or redistributed by this dataset.

## Reproducibility design

```text
baseline_001/{queries.jsonl,answers.jsonl,judge_votes.jsonl,traces/...}
                                 |
                                 v
                         analyze_lattes.py
                                 |
                                 v
             baseline_001/derived/analysis/*.csv
                                 |
                    +------------+------------+
                    |                         |
                    v                         v
          generate_figures.py           analysis.ipynb
                    |                         |
                    v                         v
 baseline_001/derived/figures/      interactive inspection
```

`analyze_lattes.py` reads the preserved baseline, invokes `extract_observed_calls.py`, and generates normalized CSV files and a provenance manifest.

`generate_figures.py` consumes only the derived analysis files. `analysis.ipynb` is an inspection layer over the generated CSV files.

The workflow does not compare its results against values copied from the articles.

## Directory layout

```text
experiments/lattes/
├── README.md
├── experiment.baseline001.json
├── analyze_lattes.py
├── extract_observed_calls.py
├── generate_figures.py
├── analysis.ipynb
└── baseline_001/
    ├── provenance.json
    ├── manifest.json
    ├── queries.jsonl
    ├── answers.jsonl
    ├── evals.jsonl
    ├── evals-summary.json
    ├── judge_votes.jsonl
    └── traces/
        ├── queries/
        └── evals/
```

The software and dataset snapshots associated with this baseline are stored at the repository root:

```text
tools/llmcontextbench-lattes.zip
datasets/lattes.tar.gz
```

Their relationship to the execution is recorded in `baseline_001/provenance.json`.

## Generated analysis files

Running the analysis creates:

```text
baseline_001/derived/analysis/
├── lattes_trials.csv
├── lattes_summary_by_configuration.csv
├── lattes_summary_by_model.csv
├── lattes_summary_by_question.csv
├── lattes_summary_by_curriculum.csv
├── lattes_summary_by_tag.csv
├── lattes_summary_by_judge.csv
├── table-5.csv
├── table-6.csv
├── table-7.csv
└── lattes_analysis_manifest.json
```

The `table-*.csv` files correspond to Tables 5, 6, and 7 of the research-track paper. Their numerical values are calculated directly from the preserved baseline.

Observed operation calls are extracted into:

```text
baseline_001/derived/calls/
├── observed_tool_calls_by_run.csv
├── observed_tool_calls_long.csv
└── observed_tool_calls_summary.csv
```

## Generated figures

Running `generate_figures.py` creates PDF, PNG, and SVG versions of:

```text
baseline_001/derived/figures/
├── figure-3a-latency-violin.*
├── figure-3b-question-accuracy-heatmap.*
└── figure-3-combined.*
```

It also writes the plotted data:

```text
figure-3a-latency-data.csv
figure-3b-heatmap-data.csv
```

## Requirements

Offline analysis requires Python 3.11 or 3.12 and the packages listed in the root `requirements-analysis.txt`. Jupyter is necessary only for the notebook.

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-analysis.txt
```

Offline processing does not call model providers or the remote MCP server.

## Reproduce Tables 5–7 and Figure 3

Run the complete workflow from the repository root:

```bash
just lattes-all
```

The stages can also be run separately:

```bash
just lattes-analyze
just lattes-figures
```

Equivalent direct commands:

```bash
python experiments/lattes/analyze_lattes.py \
  experiments/lattes/baseline_001 \
  --output-dir experiments/lattes/baseline_001/derived/analysis

python experiments/lattes/generate_figures.py \
  experiments/lattes/baseline_001/derived/analysis \
  --output-dir experiments/lattes/baseline_001/derived/figures
```

To generate selected figures:

```bash
python experiments/lattes/generate_figures.py \
  experiments/lattes/baseline_001/derived/analysis \
  --output-dir experiments/lattes/baseline_001/derived/figures \
  --only latency heatmap
```

Valid values for `--only` are `latency`, `heatmap`, and `combined`.

## Inspect the derived results in Jupyter

Generate the CSV files and open the notebook:

```bash
just lattes-analyze
jupyter lab experiments/lattes/analysis.ipynb
```

For non-interactive execution:

```bash
just lattes-notebook
```

## Inspect observed operation calls

The main analysis invokes call extraction automatically. To execute it independently:

```bash
python experiments/lattes/extract_observed_calls.py \
  experiments/lattes/baseline_001 \
  --output-dir experiments/lattes/baseline_001/derived/calls
```

## Clean generated outputs

```bash
just lattes-clean
```

## Re-running the experiment

The preserved artifacts are sufficient for offline analytical replication. Re-running the complete experiment requires provider credentials, a compatible remote MCP server, network access, rate limits, budget, and the archived software and dataset snapshots.
