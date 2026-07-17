# LLMContextBench Replication Package

This repository is the replication package for the empirical studies conducted with **LLMContextBench**, a benchmark tool for evaluating how LLM-based systems receive and access context.

LLMContextBench models an experiment as a combination of dataset instances, tasks, models, context-provisioning strategies, formats, repetitions, evaluation procedures, and execution traces. The tool supports reproducible comparisons between strategies such as inline context, local function calling, local MCP, and remote MCP.

The package contains the preserved outputs, dataset snapshots, analysis scripts, and figure/table generators used in the following SBES 2026 papers:

- *LLMContextBench: A Benchmark Tool for Evaluating Context Provisioning Strategies in LLM-Based Systems*;
- *Evaluating Context Provisioning Strategies for LLM-Based Systems: An Empirical Study with the Lattes Platform*.

## 1. Purpose and relation to the papers

The repository supports two complementary uses:

1. **Offline replication**, which reprocesses the committed experimental outputs without contacting model providers or MCP servers. This is the recommended path for artifact evaluation.
2. **Full experiment re-execution**, which requires the archived datasets and tool versions, model credentials, external services, time, and budget.

The two preserved experiments are:

| Experiment | Domain | Evaluation | Main reproduced artifacts |
|---|---|---|---|
| Lattes | Academic CV question answering | Three LLM judges | Research-paper Tables 5–7 and Figure 3 |
| RepoQA | Long-context source-code retrieval | Deterministic RepoQA scorer | Analysis-ready CSV files and diagnostic summaries |

## 2. Repository structure

```text
.
├── README.md
├── justfile
├── requirements-analysis.txt
├── datasets/
│   ├── lattes.tar.gz
│   └── repoqa.tar.gz
├── tools/
│   └── llmcontextbench-lattes.zip
│   └── llmcontextbench-current.zip
├── expected/
│   ├── table-5-lattes.csv
│   └── table-3b-repoqa.csv
└── experiments/
    ├── lattes/
    │   ├── README.md
    │   ├── analyze_lattes.py
    │   ├── extract_observed_calls.py
    │   ├── generate_figures.py
    │   ├── analysis.ipynb
    │   └── baseline_001/
    ├── repoqa/
    │   ├── README.md
    │   ├── analyze_repoqa.py
    │   ├── derive_repoqa.py
    │   ├── build_table_3b.py
    │   ├── generate_figures.py
    │   └── baseline-01/
    └── tool-paper/
```

The baseline directories contain the preserved raw outputs. Generated files are written below each baseline's `derived/` directory and can be safely removed and recreated.

More detailed experiment-specific documentation is available in:

- [`experiments/lattes/README.md`](experiments/lattes/README.md);
- [`experiments/repoqa/README.md`](experiments/repoqa/README.md).

## 3. Setup

### Requirements

- Python 3.11 or 3.12;
- [`just`](https://github.com/casey/just);
- Python packages listed in `requirements-analysis.txt`;
- Jupyter only when executing the Lattes notebook.

Create an isolated environment from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-analysis.txt
```

Confirm the available reproduction commands:

```bash
just --version
just --list
```

A different Python executable can be supplied through the `PYTHON` environment variable:

```bash
PYTHON=python3.12 just lattes-all
```

## 4. Recommended offline replication

Offline processing reads only the committed artifacts. It does not call OpenAI, Google, Anthropic, or remote MCP services.

### Reproduce the Lattes results

Run the complete Lattes workflow:

```bash
just lattes-all
```

This performs the following pipeline:

```text
answers.jsonl + judge_votes.jsonl + traces
                    |
                    v
            analyze_lattes.py
                    |
                    v
          derived analysis CSVs
                    |
                    v
            generate_figures.py
```

The main generated analysis files are written to:

```text
experiments/lattes/baseline_001/derived/analysis/
```

They include:

- `table-5.csv` — aggregate effectiveness, cost, latency, and calls by configuration;
- `table-6.csv` — results by model and configuration;
- `table-7.csv` — question-level results and qualitative difficulty characterization;
- normalized trial- and dimension-level CSV files;
- a provenance manifest.

The paper figures are written to:

```text
experiments/lattes/baseline_001/derived/figures/
```

The main files are:

- `figure-3a-latency-violin.*`;
- `figure-3b-question-accuracy-heatmap.*`;
- `figure-3-combined.*`.

To execute individual stages:

```bash
just lattes-analyze
just lattes-figures
```

To verify the generated Table 5 against the committed paper-value fixture:

```bash
just lattes-verify
```

The expected CSV is used only after the metrics have been calculated. It is never used to fill, select, or modify experimental results.

### Analyze the RepoQA baseline

Run:

```bash
just repoqa-analyze
```

This joins the preserved `responses.jsonl` and deterministic `evals.jsonl` files and writes analysis-ready outputs to:

```text
experiments/repoqa/baseline-01/derived/analysis/
```

The generated files include:

- `repoqa_trials.csv`;
- `repoqa_summary_by_configuration.csv`;
- `repoqa_summary_by_model.csv`;
- `repoqa_summary_by_language.csv`;
- `repoqa_summary_by_context_size.csv`;
- `repoqa_failures.csv`;
- `repoqa_incomplete_trials.csv`;
- `repoqa_analysis_manifest.json`.


### Reproduce all currently supported outputs

```bash
just all
```

This runs the complete Lattes workflow and the RepoQA baseline analysis.

## 5. Inspecting the Lattes notebook

The notebook is an inspection layer over the CSV files generated by `analyze_lattes.py`; it does not recompute the official metrics from raw artifacts.

Interactive use:

```bash
just lattes-analyze
jupyter lab experiments/lattes/analysis.ipynb
```

Non-interactive execution:

```bash
just lattes-notebook
```

## 6. Cleaning generated files

Remove only Lattes-derived outputs:

```bash
just lattes-clean
```

Remove only RepoQA-derived outputs:

```bash
just repoqa-clean
```

Remove all generated outputs:

```bash
just clean
```

The commands do not remove the committed baseline artifacts, dataset archives, or expected-value fixtures.

## 7. Full experiment re-execution

Re-running the complete experiments is optional and substantially more demanding than offline replication. It requires:

- the exact dataset snapshots under `datasets/`;
- the exact LLMContextBench software snapshot used by the baseline;
- provider credentials for the configured models;
- network access, provider quotas, and budget;
- compatible local or remote MCP services where applicable.

Hosted models may change over time, so a new execution is not expected to be byte-for-byte identical to the preserved baseline. For analytical replication, the committed baseline artifacts are authoritative.

The Lattes experiment is already bound to an archived tool snapshot. The RepoQA provenance still records the absence of the exact producing software snapshot as an archival limitation.

## 8. Reproducibility principles

The package follows these rules:

- preserved raw artifacts are the source of truth;
- derived CSV files are generated by deterministic scripts;
- figure generators consume derived analysis data rather than paper values;
- expected values are verification-only fixtures;
- missing measurements remain missing and are explicitly reported;
- generated files are separated from committed baseline artifacts;
- full experiment re-execution is distinguished from offline analytical replication.

## 9. Citation

Citation metadata will be added after the final publication information and persistent artifact identifier are available.
