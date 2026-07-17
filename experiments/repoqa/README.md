# RepoQA experiment

This directory contains the preserved RepoQA experiment used in the SBES 2026 Tools Track paper **LLMContextBench: A Benchmark Tool for Evaluating Context Provisioning Strategies in LLM-Based Systems**.

RepoQA evaluates long-context source-code retrieval. Given a natural-language description of a target function and repository-level code context, the model must reproduce the target function. Evaluation is deterministic: the RepoQA scorer records retrieval hit, pass/fail, and code similarity rather than using LLM judges.

## Reproducibility design

The supported workflow analyzes the complete committed baseline:

```text
baseline-01/{responses.jsonl,evals.jsonl}
                     |
                     v
              derive_repoqa.py
                     |
                     v
baseline-01/derived/analysis/*.csv
```

`derive_repoqa.py` reads the preserved responses and deterministic evaluations and writes normalized CSV files and a provenance manifest. The shared parsing and summarization functions are implemented in `analyze_repoqa.py`.

The workflow does not compare generated metrics against values copied from the article.

## Experiment scope

The preserved outputs cover:

- Python, Java, TypeScript, and Rust;
- 4k, 8k, and 16k context sizes;
- OpenAI and Google generation models;
- inline code (`I-Code`);
- inline JSON (`I-JSON`);
- local function calling (`Func.`);
- local MCP (`L-MCP`).

The deterministic analysis includes:

- retrieval hit;
- scorer pass/fail;
- best similarity score;
- token consumption;
- execution duration;
- observed operation-call count.

## Directory layout

```text
experiments/repoqa/
├── README.md
├── experiment.repoqa.json
├── analyze_repoqa.py
├── derive_repoqa.py
└── baseline-01/
    ├── provenance.json
    ├── manifest.json
    ├── trials.jsonl
    ├── responses.jsonl
    ├── evals.jsonl
    ├── evals-summary.json
    └── traces/
```

The archived dataset and software snapshot are stored at the repository root:

```text
datasets/repoqa.tar.gz
tools/llmcontextbench-current.zip
```

Their relationship to the experiment and any archival limitations are recorded in `baseline-01/provenance.json`.

## Requirements

Offline processing requires Python 3.11 or 3.12 and the packages listed in the root `requirements-analysis.txt`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-analysis.txt
```

Offline analysis does not call model providers or MCP services.

## Analyze the committed baseline

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
baseline-01/derived/analysis/
├── repoqa_trials.csv
├── repoqa_summary_by_configuration.csv
├── repoqa_summary_by_model.csv
├── repoqa_summary_by_language.csv
├── repoqa_summary_by_context_size.csv
├── repoqa_failures.csv
├── repoqa_incomplete_trials.csv
└── repoqa_analysis_manifest.json
```

The manifest records SHA-256 hashes for the preserved response and evaluation files, trial counts, configurations, models, languages, context sizes, and completeness information.

Some preserved evaluations may not contain every metric required by the aggregate analysis. Such rows remain in `repoqa_trials.csv`, are marked explicitly as incomplete, and are also written to `repoqa_incomplete_trials.csv`. Missing measurements are not converted into failures.

## Interpretation of the main fields

| Field | Meaning |
|---|---|
| `hit` | Whether the best function identified by the deterministic scorer matches the requested target. |
| `passed` | Whether the response satisfies the RepoQA scoring threshold. |
| `similarity` | Best similarity score reported by the RepoQA scorer. |
| `total_tokens` | Query-phase token count preserved with the response. |
| `duration_sec` | Query execution duration in seconds. |
| `calls` | Observed operation/tool-call count. |
| `analysis_complete` | Whether all fields required for aggregate analysis are available. |
| `incomplete_reasons` | Semicolon-separated reasons for an incomplete analysis row. |

## Clean generated outputs

```bash
just repoqa-clean
```

## Re-running the experiment

The preserved artifacts support offline analytical replication. A new end-to-end execution requires a compatible LLMContextBench version, the RepoQA dataset, model credentials, network access, provider quotas, and sufficient budget. Hosted model behavior may change, so a new run is not expected to reproduce the preserved responses byte-for-byte.
