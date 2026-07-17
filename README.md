# LLMContextBench Replication Package

This repository is the replication package for the empirical studies conducted with **LLMContextBench**, a benchmark tool for evaluating how LLM-based systems receive and access external context. It allows (a) reprocessing the preserved experiment outputs offline to reproduce every table and figure reported in the papers, and (b) re-running the original experiments end to end against live model providers and MCP servers.

LLMContextBench represents an experiment as a combination of dataset instances, tasks, models, context-provisioning strategies, formats, repetitions, evaluation procedures, and execution traces. It supports comparisons between strategies such as inline context, local function calling, local MCP, and remote MCP.

The package contains preserved experiment outputs, dataset and tool snapshots, analysis scripts, and figure/table generators associated with the following SBES 2026 papers:

- *LLMContextBench: A Benchmark Tool for Evaluating Context Provisioning Strategies in LLM-Based Systems*;
- *Evaluating Context Provisioning Strategies for LLM-Based Systems: An Empirical Study with the Lattes Platform*.

The camera-ready PDFs of both papers are available in [experiments repository](https://github.com/michelav/llmcontextbench-sbes2026/) under [`articles/`](articles/).

## 1. Purpose and relation to the papers

The repository supports two complementary uses:

1. **Offline analytical replication**, which reprocesses the committed experimental outputs without contacting model providers or MCP servers. This is the recommended path for artifact evaluation.
2. **Full experiment re-execution**, which requires the archived datasets and tool versions, model credentials, external services, time, and budget.

The two preserved experiments are:

| Experiment | Domain | Evaluation | Main reproduced artifacts |
|---|---|---|---|
| Lattes | Academic CV question answering | Three LLM judges | Research-paper Tables 5–7 and Figure 3 |
| RepoQA | Long-context source-code retrieval | Deterministic RepoQA scorer | Analysis-ready CSV files and diagnostic summaries |

The analysis scripts calculate their outputs directly from the preserved experiment artifacts.

### Data provenance, storage, and ethical notes

- **Lattes dataset** (`datasets/lattes.tar.gz`; preserved outputs under `experiments/lattes/baseline_001/`) is built from curricula publicly accessible on the Brazilian Lattes Platform, each identified by its public numeric Lattes ID. No information beyond what each researcher already publishes on their own public CV page was collected or is redistributed. The compressed archive is about 1.4 MB; the full preserved baseline (`answers.jsonl`, `judge_votes.jsonl`, `queries.jsonl`, and the request/response traces kept for provenance) is about 113 MB.
- **RepoQA dataset** (`datasets/repoqa.tar.gz`; preserved outputs under `experiments/repoqa/baseline-01/`) is built from publicly available open-source repositories. The compressed archive is about 17 MB; the full preserved baseline, including traces, is about 78 MB.
- The repository totals approximately 300 MB, mostly the preserved `traces/` directories. They are not required to reproduce the tables and figures (only the derived CSV files are) and can be deleted locally if disk space is constrained; the committed baseline artifacts are otherwise the ones that matter.

## 2. Repository structure

```text
.
├── README.md
├── LICENSE
├── CITATION.cff
├── justfile
├── requirements-analysis.txt
├── articles/
│   └── README.md
├── datasets/
│   ├── lattes.tar.gz
│   └── repoqa.tar.gz
├── tools/
│   ├── llmcontextbench-lattes.zip
│   └── llmcontextbench-current.zip
└── experiments/
    ├── lattes/
    │   ├── README.md
    │   ├── analyze_lattes.py
    │   ├── extract_observed_calls.py
    │   ├── generate_figures.py
    │   ├── analysis.ipynb
    │   └── baseline_001/
    └── repoqa/
        ├── README.md
        ├── analyze_repoqa.py
        ├── derive_repoqa.py
        └── baseline-01/
```

The baseline directories contain the preserved raw outputs. Generated files are written below each baseline's `derived/` directory and can be safely removed and recreated.

Experiment-specific documentation is available in:

- [`experiments/lattes/README.md`](experiments/lattes/README.md);
- [`experiments/repoqa/README.md`](experiments/repoqa/README.md).

## 3. Setup

### Requirements

- Python 3.11 or 3.12;
- [`just`](https://github.com/casey/just);
- Python packages listed in `requirements-analysis.txt` (this includes `jupyterlab` and `nbconvert`, needed to open or non-interactively execute the Lattes notebook);
- no GPU, Docker, or platform-specific dependencies are required for offline replication; it runs on Linux, macOS, or WSL;
- about 350 MB of free disk space for the repository content (see [Section 1](#data-provenance-storage-and-ethical-notes) for a breakdown), plus roughly 450–500 MB for the Python virtual environment and its dependencies (mostly Jupyter and its transitive packages) — budget about 1 GB of free disk space in total.

### Installation

Create an isolated environment from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-analysis.txt
```

Check the available commands:

```bash
just --version
just --list
```

A different Python executable can be supplied through the `PYTHON` environment variable:

```bash
PYTHON=python3.12 just lattes-all
```

**NixOS / Nix users:** a plain `python -m venv` followed by `pip install` may fail to import `numpy`/`pandas` with an error such as `ImportError: libstdc++.so.6: cannot open shared object file`, because prebuilt wheels expect system libraries that Nix does not expose on the standard path. Use a Nix shell with the required packages instead of the venv steps above:

```bash
nix-shell -p just -p 'python3.withPackages(ps: with ps; [ numpy pandas jupyterlab matplotlib ])' --run 'just lattes-all'
```

This has been verified to run the full offline workflow (`lattes-all`, `repoqa-analyze`, `lattes-notebook`) without errors.

**Verify the installation** by running the complete offline Lattes workflow once:

```bash
just lattes-all
```

Expected output: the console prints a per-configuration summary table (`I-HTML`, `I-JSON`, `Func.`, `L-MCP`, `R-MCP`), and the following files are created:

```text
experiments/lattes/baseline_001/derived/analysis/table-5.csv
experiments/lattes/baseline_001/derived/figures/figure-3-combined.png
```

If both appear, the environment is installed correctly.

## 4. Recommended offline replication

Offline processing reads only the committed artifacts. It does not call OpenAI, Google, Anthropic, or remote MCP services.

### Reproduce the Lattes results

Run the complete Lattes workflow:

```bash
just lattes-all
```

The workflow is:

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

The figures are written to:

```text
experiments/lattes/baseline_001/derived/figures/
```

The main files are:

- `figure-3a-latency-violin.*`;
- `figure-3b-question-accuracy-heatmap.*`;
- `figure-3-combined.*`.

Individual stages can be executed with:

```bash
just lattes-analyze
just lattes-figures
```

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

The notebook is an inspection layer over the CSV files generated by `analyze_lattes.py`; it does not recompute the official metrics from raw artifacts. Its Figure 3 cells import `generate_figures.py` and call its drawing functions directly (`load_analysis`, `draw_latency_violin`, `draw_accuracy_heatmap`), so the notebook and the standalone script render the exact same figures — only the destination (inline display vs. saved files) differs.

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

These commands do not remove the committed baseline artifacts, dataset archives, or tool snapshots.

## 7. Full experiment re-execution

Re-running the complete experiments is optional and substantially more demanding than offline replication. It requires:

- the exact dataset snapshots under `datasets/`;
- the exact LLMContextBench software snapshot used by the baseline;
- provider credentials for the configured models;
- network access, provider quotas, and budget;
- compatible local or remote MCP services where applicable.

Hosted models may change over time, so a new execution is not expected to be byte-for-byte identical to the preserved baseline. For analytical replication, the committed baseline artifacts are authoritative.

The Lattes experiment is bound to an archived tool snapshot. The RepoQA provenance records the available software and dataset information and any remaining archival limitations.

**LLMContextBench itself is under active development.** The `tools/*.zip` archives are frozen snapshots pinned to the baselines preserved in this replication package; they are what analytical and full re-execution replication should use. The latest, actively developed version of the tool is maintained separately at <https://github.com/michelav/llmcontextbench>.

## 8. Reproducibility principles

The package follows these rules:

- preserved raw artifacts are the source of truth;
- derived CSV files are generated by deterministic scripts;
- figure generators consume derived analysis data rather than article values;
- missing measurements remain missing and are explicitly reported;
- generated files are separated from committed baseline artifacts;
- full experiment re-execution is distinguished from offline analytical replication.

## 9. Citation

Citation metadata is provided in [`CITATION.cff`](CITATION.cff). GitHub can render this file through the repository's **Cite this repository** action; Zenodo parses the same file to populate the deposit's citation and "Cite as" fields.

Until a DOI is assigned, cite the repository using its URL and the version or commit used in the analysis. After the first Zenodo deposit:

- update `CITATION.cff` with the assigned DOI (`identifiers`) and the deposited `version`;
- update this README and the papers' *Artifact Availability* statements to point to the specific archived version (for example, `https://doi.org/10.5281/zenodo.NNNNNNN`), not the "all versions" concept DOI, per the CBSoft Festival de Artefatos submission instructions.

## 10. License

Repository-authored source code, analysis scripts, and documentation are distributed under the [MIT License](LICENSE).

The preserved Lattes and RepoQA dataset archives (`datasets/*.tar.gz`) were assembled by the authors from publicly accessible sources (public Lattes Platform curricula and public open-source repositories, respectively; see [Section 1](#data-provenance-storage-and-ethical-notes)) and are made available for research and replication purposes under the same repository terms.

Tool snapshots, raw model outputs, and any other third-party or derived artifacts may still be subject to their original licenses, terms of use, or attribution requirements. The MIT License does not override rights attached to material created by third parties.
