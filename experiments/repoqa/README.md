# RepoQA Experiment

This directory contains the RepoQA experiment used in the SBES 2026 Tools Track paper:

- **LLMContextBench: A Benchmark Tool for Evaluating Context Provisioning Strategies in LLM-Based Systems**.

RepoQA evaluates long-context source-code retrieval. Given a natural-language description of a target function and a repository-level code context, the model must reproduce the exact target function. Unlike the Lattes experiment, RepoQA uses a deterministic dataset-specific scorer rather than LLM judges.

## Experiment scope

The preserved experiment covers:

- Python, Java, TypeScript, and Rust repositories;
- context sizes represented in the instance identifiers, including 4k, 8k, and 16k;
- four generation models from OpenAI and Google;
- inline code, inline JSON, local function calling, and local MCP configurations in the preserved outputs;
- one repetition per planned condition;
- deterministic RepoQA scoring based on target matching and code similarity.

The complete committed output currently contains **960 responses and 960 evaluations**. The published Table 3(b), however, reports **45 trials per configuration**. Therefore, the exact immutable subset used for the paper must be recorded in a selection manifest before claiming exact reproduction of the published table. The analysis scripts intentionally do not guess this subset.

## Directory organization

```text
experiments/repoqa/
├── README.md
├── experiment.repoqa.json
├── analyze_repoqa.py
├── generate_figures.py
├── paper-selection.example.json
├── expected/
│   └── tool-paper-table-3b.csv
└── baseline-01/
    ├── manifest.json
    ├── trials.jsonl
    ├── responses.jsonl
    ├── evals.jsonl
    ├── evals-summary.json
    └── traces/
        └── executions/
```

The exact RepoQA dataset snapshot committed for this artifact is:

```text
datasets/repoqa.tar.gz
```

Before the final archival release, the exact LLMContextBench software snapshot that produced this baseline should also be stored in `tools/` and bound to the experiment through a portable provenance file.

## Main experiment artifacts

### `experiment.repoqa.json`

The declarative experiment configuration. It identifies the dataset, task, generation models, strategies, tracing options, and evaluation settings.

The configuration currently committed must be reconciled with the preserved outputs before the final release. In particular, the paper and output artifacts contain both inline code and inline JSON configurations, while the current factor declaration may not completely describe every preserved condition. Preserve the historical file, but add a corrected reproduction configuration or a provenance explanation rather than silently changing the original experiment record.

### `baseline-01/manifest.json`

The execution manifest produced during planning. It records dataset identity, evaluation settings, artifact settings, and tracing options. It contains absolute paths from the original machine; those paths are historical metadata and are not required for offline processing.

### `baseline-01/trials.jsonl`

The planned experimental conditions. Each record should bind an instance, task, model, strategy, format, and repetition. It is the canonical input for a complete re-execution with the archived tool version.

### `baseline-01/responses.jsonl`

The generated source-code responses and query-phase measurements. Relevant fields include:

- `trialId`;
- `instanceId`;
- `modelId`, `model`, and `provider`;
- `strategy` and `format`;
- generated `response`;
- `usage.totalTokens`;
- `timing.durationMs`;
- `metricsSummary.toolCalls`, `functionCalls`, and `mcpToolCalls`;
- `traceRef`.

Use this file for token cost, latency, model-level, strategy-level, and operation-call analyses.

### `baseline-01/evals.jsonl`

One deterministic evaluation per response. RepoQA-specific results are stored under `details.repoqa`, including:

- `isBestMatch`: whether the best matching function is the requested target;
- `passed`: whether the similarity satisfies the configured scoring policy;
- `bestSimilarScore`: similarity between the response and the best target candidate;
- `bestTarget` and `target`;
- `language`, repository, threshold, and comment-handling policy.

No judge model is used for this experiment.

### `baseline-01/evals-summary.json`

A compact evaluation index. The committed file reports 960 evaluated items and can be used for a quick completeness check.

### `baseline-01/traces/executions/`

Detailed execution traces. Depending on strategy and model provider, traces may contain prompts, raw provider responses, operation calls, outputs, token accounting, timing, retries, and errors.

## Metrics used in the tool paper

The RepoQA portion of Table 3 uses the following definitions:

| Metric | Definition |
|---|---|
| `N` | Number of selected trials for the configuration. |
| `Hit` | Percentage with `details.repoqa.isBestMatch = true`. |
| `Pass` | Percentage with `details.repoqa.passed = true`. |
| `Sim.` | Mean `details.repoqa.bestSimilarScore`. |
| `Tok./T` | Total query-phase tokens divided by all selected trials. |
| `Tok./P` | Total query-phase tokens divided by passing trials. |
| `Sec.` | Median query duration in seconds. |
| `Calls` | Mean operation/tool-call count from response metrics. |

Evaluation is deterministic and does not consume judge-model tokens.

## Requirements for offline processing

Recommended:

- Python 3.11 or 3.12;
- pandas;
- NumPy;
- Matplotlib.

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-analysis.txt
```

Offline analysis reads only committed outputs. It does not call model providers or MCP services.

## Analyze the complete committed baseline

Run from the repository root:

```bash
python experiments/repoqa/analyze_repoqa.py \
  experiments/repoqa/baseline-01
```

By default, results are written to:

```text
experiments/repoqa/baseline-01/derived/analysis/
```

Generated files include:

```text
repoqa_trials.csv
repoqa_summary_by_configuration.csv
repoqa_summary_by_model.csv
repoqa_summary_by_language.csv
repoqa_summary_by_context_size.csv
repoqa_failures.csv
tool-paper-table-3b.csv
tool-paper-table-3b.tex
repoqa_analysis_manifest.json
```

The complete 960-trial baseline is useful for broader diagnostics, but it is not automatically the same population reported as `N = 45` per configuration in the paper.

## Reproduce the published RepoQA table

First copy the example selection manifest:

```bash
cp experiments/repoqa/paper-selection.example.json \
  experiments/repoqa/paper-selection.json
```

Populate it with the exact trial IDs or immutable filters corresponding to the paper. Do not leave it as an empty selection while claiming paper reproduction.

Then run:

```bash
python experiments/repoqa/analyze_repoqa.py \
  experiments/repoqa/baseline-01 \
  --selection experiments/repoqa/paper-selection.json \
  --expected experiments/repoqa/expected/tool-paper-table-3b.csv \
  --verify
```

The command returns a non-zero status when the selected results do not reproduce the published values within the documented numerical tolerances.

## Generate supporting RepoQA figures

```bash
python experiments/repoqa/generate_figures.py \
  experiments/repoqa/baseline-01
```

The default output directory is:

```text
experiments/repoqa/baseline-01/derived/figures/
```

The script generates PDF, PNG, and SVG versions of:

- retrieval hit and pass rates;
- quality–token-cost trade-off;
- pass rate by context size;
- pass rate by programming language;
- latency distribution;
- mean-similarity heatmap.

These are supporting diagnostic figures. The numbered Figures 1 and 2 in the tool paper are conceptual tool diagrams and are generated separately by `experiments/tool-paper/generate_figures.py`.

To apply the exact paper selection:

```bash
python experiments/repoqa/generate_figures.py \
  experiments/repoqa/baseline-01 \
  --selection experiments/repoqa/paper-selection.json
```

## Generate all tool-paper artifacts

After creating the exact RepoQA selection manifest:

```bash
make reproduce-tool-paper \
  REPOQA_SELECTION=experiments/repoqa/paper-selection.json
```

This regenerates:

- the RepoQA analyses;
- the supporting RepoQA figures;
- the combined Lattes/RepoQA Table 3;
- code-generated versions of the conceptual domain-model and workflow figures.

## Re-execute the experiment from the beginning

Offline processing is the recommended artifact-evaluation path. A complete rerun is optional and requires external services, time, and budget.

### 1. Extract the dataset

```bash
mkdir -p .artifact-work/repoqa-dataset

tar -xzf datasets/repoqa.tar.gz \
  -C .artifact-work/repoqa-dataset
```

### 2. Install the exact software snapshot

Before the archival release, add the exact software archive used by the RepoQA baseline under `tools/`, extract it, and install the locked environment provided by that snapshot. Do not substitute the current `main` branch when claiming exact reproduction.

The current public CLI vocabulary is typically:

```text
ctxbench plan
ctxbench execute
ctxbench eval
ctxbench export
ctxbench status
```

Use the commands documented by the archived snapshot if they differ.

### 3. Configure model credentials

The preserved configuration uses OpenAI and Google models. Configure the variables expected by the archived adapters, commonly:

```bash
export OPENAI_API_KEY="..."
export GOOGLE_API_KEY="..."
```

Some Google adapter versions may use `GEMINI_API_KEY`. Follow the documentation inside the archived software snapshot. Never commit credentials.

### 4. Configure MCP when required

The preserved factors include local MCP. Local MCP normally uses an in-process or local client/server boundary and should not require a public endpoint. The configuration also contains remote MCP parameters. If a reproduction configuration enables remote MCP, it additionally requires:

```bash
export REPOQA_MCP_TOKEN="..."
```

and a compatible MCP server exposing the same repository operations and dataset snapshot. Do not place the token directly in the JSON configuration.

### 5. Run the lifecycle

Using a verified working copy of the experiment configuration and the archived CLI:

```bash
ctxbench plan experiments/repoqa/experiment.repoqa.json \
  --output .artifact-work/repoqa-rerun

ctxbench execute .artifact-work/repoqa-rerun/trials.jsonl
ctxbench eval .artifact-work/repoqa-rerun/responses.jsonl

ctxbench export .artifact-work/repoqa-rerun/evals.jsonl \
  --to csv \
  --output .artifact-work/repoqa-rerun/results.csv

ctxbench status .artifact-work/repoqa-rerun
```

Hosted model changes may prevent byte-for-byte or numerically exact equality with the preserved outputs. The committed response and evaluation artifacts remain the reference for offline analytical reproduction.

## Known release blockers

Before assigning a DOI to the final artifact:

1. bind the baseline to an exact software archive and checksum;
2. add a SHA-256 checksum for `datasets/repoqa.tar.gz`;
3. reconcile the committed experiment configuration with the preserved formats and configurations;
4. identify and version the exact 45-trial-per-configuration paper subset, or correct the paper/table if `N = 45` is no longer the intended result;
5. run the analysis and verification commands in a clean environment;
6. inspect traces for credentials, private paths, or other unintended information.
