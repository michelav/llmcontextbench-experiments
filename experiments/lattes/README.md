# Lattes Experiments

This directory contains the Lattes experiments used in the following SBES 2026 papers:

- **Evaluating Context Provisioning Strategies for LLM-Based Systems: An Empirical Study with the Lattes Platform** — Research Track.
- **LLMContextBench: A Benchmark Tool for Evaluating Context Provisioning Strategies in LLM-Based Systems** — Tools Track.

The main experiment is `baseline_001`, which compares five effective context-provisioning configurations over the same Lattes curricula, questions, generation models, and evaluation procedure:

- inline HTML;
- inline JSON;
- local function calling;
- local MCP;
- remote MCP.

The preserved baseline contains:

- 5 Lattes curriculum instances;
- 12 benchmark questions;
- 4 answer-generation models;
- 5 effective strategy/format configurations;
- 1 repetition per condition;
- 1,200 generated answers;
- 1,200 aggregate evaluations;
- 3,600 individual judge votes from 3 judge models.

## Directory organization

```text
experiments/lattes/
├── README.md
├── experiment.baseline001.json
├── analysis.ipynb
├── extract_observed_calls.py
├── generate_figures.py
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

The exact software and dataset snapshots used by the baseline are stored at the repository root:

```text
tools/llmcontextbench-lattes.zip
datasets/lattes.tar.gz
```

Their relationship to `baseline_001` is recorded in `baseline_001/provenance.json`. These embedded archives are the authoritative versions for reproducing this baseline; the current state of an external repository must not be silently substituted for them.

## Main experiment artifacts

### `experiment.baseline001.json`

The declarative experiment configuration. It defines:

- the five Lattes instances;
- the twelve questions;
- the four generation models;
- the three judge models;
- the context-provisioning strategies and formats;
- tracing and evaluation settings;
- the remote MCP endpoint configuration;
- one repetition per experimental condition.

The file is preserved as part of the original experiment. Some names in it reflect the historical version of the benchmark tool.

### `baseline_001/provenance.json`

A portable provenance record for the experiment. It binds the baseline to:

- `tools/llmcontextbench-lattes.zip`, the exact software snapshot used by the experiment;
- `datasets/lattes.tar.gz`, the exact dataset snapshot used by the experiment;
- the experiment configuration;
- the expected numbers of planned queries, answers, evaluations, and judge votes.

### `baseline_001/manifest.json`

The execution manifest generated during experiment planning. It records the experiment identifier, judge configuration, artifact settings, and trace configuration used by the historical execution.

The original manifest contains an absolute path from the machine on which the experiment was run. That path is retained only as historical metadata and is not required for offline analysis. Portable provenance is provided by `provenance.json`.

### `baseline_001/queries.jsonl`

The planned query executions. Each line describes one experimental condition, including the curriculum instance, question, model, strategy, format, and repetition.

Expected number of records: **1,200**.

### `baseline_001/answers.jsonl`

The generated answers and query-execution measurements. Each line contains information such as:

- experiment and run identifiers;
- curriculum instance and question;
- provider and generation model;
- strategy and context format;
- generated answer;
- execution status;
- token usage;
- timing;
- model, function, tool, and MCP call metrics;
- trace reference.

Expected number of records: **1,200**.

Use this file for analyses of answer-generation cost, latency, model behavior, and strategy-level execution metrics.

### `baseline_001/evals.jsonl`

One aggregate evaluation record per generated answer. It summarizes the outcomes from the configured judges, including:

- correctness rating;
- completeness rating;
- judge count and errors;
- evaluation token usage and duration;
- evaluation status;
- evaluation trace reference.

Expected number of records: **1,200**.

### `baseline_001/evals-summary.json`

A compact summary of the aggregate evaluations. It is useful for quickly checking that the expected evaluated runs are present without scanning the complete JSONL file.

### `baseline_001/judge_votes.jsonl`

The individual judge-level assessments used to derive majority, unanimous, disagreement, and inter-judge agreement results.

Each generated answer is evaluated by three judges. Expected number of records: **3,600**.

Use this file for:

- majority and unanimous correctness;
- per-judge results;
- judge disagreement;
- weighted kappa;
- same-provider judge-bias checks;
- qualitative inspection of judge justifications.

### `baseline_001/traces/queries/`

Detailed traces for answer generation. Depending on strategy and provider capabilities, traces may contain:

- rendered prompts;
- model calls and raw provider responses;
- local function calls;
- local MCP calls;
- provider-native remote MCP evidence;
- tool arguments and outputs;
- usage and timing measurements;
- errors and retries.

These traces are especially important for checking call behavior and observability differences among local function calling, local MCP, and remote MCP.

### `baseline_001/traces/evals/`

Detailed evaluation traces. They contain judge calls, judge responses, token usage, timing, errors, and other evaluation-level evidence.

### `extract_observed_calls.py`

Extracts observed function, tool, and MCP call evidence from the query traces. It handles locally controlled calls and provider-native remote MCP evidence.

It generates:

```text
observed_tool_calls_by_run.csv
observed_tool_calls_long.csv
observed_tool_calls_summary.csv
```

- `observed_tool_calls_by_run.csv`: one row per answer run, with compact call metrics and call observability information;
- `observed_tool_calls_long.csv`: one row per observed call, including operation name, source, arguments, status, duration, and output size;
- `observed_tool_calls_summary.csv`: grouped call statistics by provider, model, strategy, and format.

### `generate_figures.py`

Regenerates the main quantitative figures from `answers.jsonl` and `judge_votes.jsonl`:

- question-by-strategy majority-accuracy heatmap;
- latency distribution by strategy;
- quality/token-cost Pareto trade-off;
- question-level disagreement chart.

The script writes PDF and PNG versions of each figure.

### `analysis.ipynb`

Notebook for interactively inspecting and processing the baseline outputs. It reads the generated answers, evaluations, judge votes, and derived call CSVs to produce the tabular and statistical analyses used during paper preparation.

The command-line scripts are the preferred path for deterministic preprocessing; the notebook is intended for inspection and additional analysis.

## Requirements for offline processing

Offline processing of the preserved outputs does **not** call model providers or the MCP server.

Recommended environment:

- Python 3.11 or 3.12;
- pandas;
- NumPy;
- Matplotlib;
- Jupyter, for the notebook.

From the repository root, create an environment using your preferred package manager. For example:

```bash
python -m venv .venv
source .venv/bin/activate
pip install pandas numpy matplotlib jupyter
```

A locked repository-level environment should be preferred once `pyproject.toml` and `uv.lock` are added to the final artifact.

## Processing the preserved baseline outputs

Run all commands below from the repository root.

### 1. Check the number of records

```bash
python - <<'PY'
from pathlib import Path

root = Path("experiments/lattes/baseline_001")
for name in ["queries.jsonl", "answers.jsonl", "evals.jsonl", "judge_votes.jsonl"]:
    path = root / name
    with path.open(encoding="utf-8") as stream:
        count = sum(1 for line in stream if line.strip())
    print(f"{name}: {count}")
PY
```

Expected output:

```text
queries.jsonl: 1200
answers.jsonl: 1200
evals.jsonl: 1200
judge_votes.jsonl: 3600
```

### 2. Extract observed function, tool, and MCP calls

```bash
python experiments/lattes/extract_observed_calls.py \
  experiments/lattes/baseline_001 \
  --output-dir experiments/lattes/baseline_001/derived/calls
```

For an additional recursive check of raw provider responses for MCP evidence:

```bash
python experiments/lattes/extract_observed_calls.py \
  experiments/lattes/baseline_001 \
  --output-dir experiments/lattes/baseline_001/derived/calls \
  --scan-raw-response
```

### 3. Regenerate the figures

```bash
python experiments/lattes/generate_figures.py \
  experiments/lattes/baseline_001 \
  --output-dir experiments/lattes/baseline_001/derived/figures
```

To generate selected figures only:

```bash
python experiments/lattes/generate_figures.py \
  experiments/lattes/baseline_001 \
  --output-dir experiments/lattes/baseline_001/derived/figures \
  --only heatmap latency
```

Valid values for `--only` are:

```text
heatmap latency pareto disagreement
```

### 4. Run the analysis notebook

Start Jupyter from the repository root:

```bash
jupyter lab experiments/lattes/analysis.ipynb
```

Generate the observed-call CSVs before executing notebook cells that depend on them.

For non-interactive execution:

```bash
jupyter nbconvert \
  --to notebook \
  --execute experiments/lattes/analysis.ipynb \
  --output analysis.executed.ipynb \
  --output-dir experiments/lattes/baseline_001/derived
```

## Reproducing the experiment from the beginning

The preserved output files are sufficient to reproduce the analyses offline. Re-running all 1,200 answer-generation trials and 3,600 judge assessments is optional and has additional requirements:

- access to the configured OpenAI, Google, and Anthropic models;
- valid API credentials for each provider;
- a compatible remote MCP server;
- an MCP authentication token;
- network access;
- sufficient provider rate limits and budget;
- acceptance that SaaS model updates may produce results that differ from the preserved baseline.

### 1. Extract the exact software and dataset snapshots

From the repository root:

```bash
mkdir -p .artifact-work/tool .artifact-work/dataset

unzip tools/llmcontextbench-lattes.zip \
  -d .artifact-work/tool

tar -xzf datasets/lattes.tar.gz \
  -C .artifact-work/dataset
```

The archive contents are the authoritative versions bound to the experiment. Do not replace them with the current `main` branch of the tool or dataset when claiming exact reproduction.

### 2. Install the archived software

Enter the extracted directory that contains the archived tool's `pyproject.toml` and install its locked environment. Depending on the metadata preserved in that snapshot, use the corresponding method, for example:

```bash
uv sync --locked
```

or:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The historical package may expose the CLI as `copa`; later releases use `ctxbench`. Check the archived `pyproject.toml` or run the available command with `--help` before proceeding.

For the commands below, set the CLI name that exists in the archived snapshot:

```bash
export BENCH_CMD=copa
```

Use `ctxbench` instead only when that is the command exposed by the embedded software archive.

### 3. Place or reference the extracted dataset

The historical experiment configuration references a Lattes dataset directory. Either:

- extract or copy the embedded dataset to the path expected by a working copy of the configuration; or
- update a copy of `experiment.baseline001.json` to reference the extracted dataset path.

Do not modify the preserved original configuration when documenting or comparing the historical execution.

### 4. Configure provider credentials

Configure the environment variables required by the archived provider adapters. These commonly include:

```bash
export OPENAI_API_KEY="..."
export GOOGLE_API_KEY="..."
export ANTHROPIC_API_KEY="..."
```

Depending on the Google adapter version, the archived tool may use another documented variable such as `GEMINI_API_KEY`; follow the metadata and documentation included in the embedded software snapshot.

Never commit provider credentials to this repository.

### 5. Configure remote MCP access

The baseline includes a remote MCP configuration. A full re-execution requires a compatible MCP server exposing the same Lattes operation surface and the same dataset snapshot.

Configure at least:

```bash
export LATTES_MCP_TOKEN="..."
```

Use a working copy of the experiment configuration to set the compatible MCP server URL and any required server label or description. The token placeholder in the configuration must resolve from the environment; do not place the token directly in the JSON file.

For comparable results, the remote MCP server should expose the same read-only Lattes operations used by the local function and local MCP strategies.

### 6. Plan, execute, evaluate, and export

The historical workflow uses the legacy artifact names `queries.jsonl` and `answers.jsonl`. With the archived CLI selected in `BENCH_CMD`, the expected workflow is:

```bash
$BENCH_CMD plan \
  experiments/lattes/experiment.baseline001.json \
  --output .artifact-work/rerun/baseline_001

$BENCH_CMD query \
  .artifact-work/rerun/baseline_001/queries.jsonl

$BENCH_CMD eval \
  .artifact-work/rerun/baseline_001/answers.jsonl

$BENCH_CMD export \
  .artifact-work/rerun/baseline_001/evals.jsonl \
  --to csv \
  --output .artifact-work/rerun/baseline_001/results.csv

$BENCH_CMD status \
  .artifact-work/rerun/baseline_001
```

If the embedded snapshot exposes the newer vocabulary, use its corresponding `execute`, `trials.jsonl`, and `responses.jsonl` commands as documented inside the archive. Do not mix legacy outputs with newer outputs without an explicit conversion step.

## Reproducibility levels

This artifact supports two distinct levels of reproduction:

### Offline analytical reproduction

Recommended for artifact evaluation. It uses the preserved baseline outputs to regenerate tables, figures, call summaries, agreement analyses, and other reported statistics. It does not require provider accounts, API tokens, MCP deployment, or paid calls.

### Full experimental re-execution

Re-runs generation and evaluation from the archived software and dataset. It requires external providers, credentials, remote MCP configuration, time, and budget. Exact numerical equality is not guaranteed because hosted models and provider infrastructure can change after the original experiment.

## Security and privacy notes

- Do not commit provider or MCP tokens.
- Query and evaluation traces may contain raw provider responses and prompt content; inspect them before creating the final public archival release.
- The dataset is intended for evaluating methods and systems, not for ranking or evaluating the researchers represented in the curricula.
- Follow the dataset terms, notices, applicable data-protection rules, platform terms, and institutional research policies included with the final artifact.
