PYTHON ?= python

LATTES_DIR ?= experiments/lattes/baseline_001
LATTES_ANALYSIS_DIR ?= $(LATTES_DIR)/derived/analysis
LATTES_FIGURES_DIR ?= $(LATTES_DIR)/derived/figures
LATTES_EXPECTED ?= experiments/tool-paper/expected/table-3a-lattes.csv

REPOQA_DIR ?= experiments/repoqa/baseline-01
REPOQA_SELECTION ?=
REPOQA_EXPECTED ?= experiments/repoqa/expected/tool-paper-table-3b.csv
TOOL_PAPER_DIR ?= experiments/tool-paper/generated

SELECTION_ARG = $(if $(strip $(REPOQA_SELECTION)),--selection $(REPOQA_SELECTION),)
VERIFY_ARG = $(if $(strip $(REPOQA_SELECTION)),--expected $(REPOQA_EXPECTED) --verify,)

.PHONY: