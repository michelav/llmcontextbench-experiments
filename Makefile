PYTHON ?= python
REPOQA_DIR ?= experiments/repoqa/baseline-01
REPOQA_SELECTION ?=
REPOQA_EXPECTED ?= experiments/repoqa/expected/tool-paper-table-3b.csv
TOOL_PAPER_DIR ?= experiments/tool-paper/generated

SELECTION_ARG = $(if $(strip $(REPOQA_SELECTION)),--selection $(REPOQA_SELECTION),)
VERIFY_ARG = $(if $(strip $(REPOQA_SELECTION)),--expected $(REPOQA_EXPECTED) --verify,)

.PHONY: setup repoqa-analysis repoqa-figures tool-paper-figures tool-paper-table reproduce-tool-paper clean-derived

setup:
	$(PYTHON) -m pip install -r requirements-analysis.txt

repoqa-analysis:
	$(PYTHON) experiments/repoqa/analyze_repoqa.py \
		$(REPOQA_DIR) \
		$(SELECTION_ARG) \
		$(VERIFY_ARG)

repoqa-figures:
	$(PYTHON) experiments/repoqa/generate_figures.py \
		$(REPOQA_DIR) \
		$(SELECTION_ARG)

tool-paper-figures:
	$(PYTHON) experiments/tool-paper/generate_figures.py \
		--output-dir $(TOOL_PAPER_DIR)/figures

tool-paper-table: repoqa-analysis
	$(PYTHON) experiments/tool-paper/build_table3.py \
		--repoqa $(REPOQA_DIR)/derived/analysis/tool-paper-table-3b.csv \
		--output-dir $(TOOL_PAPER_DIR)

reproduce-tool-paper: repoqa-analysis repoqa-figures tool-paper-figures tool-paper-table
	@echo "Tool-paper analysis artifacts generated under $(REPOQA_DIR)/derived and $(TOOL_PAPER_DIR)."
	@if [ -z "$(strip $(REPOQA_SELECTION))" ]; then \
		echo "WARNING: no REPOQA_SELECTION was provided; outputs summarize the complete committed baseline and are not verified as the N=45/configuration paper subset."; \
	fi

clean-derived:
	rm -rf $(REPOQA_DIR)/derived $(TOOL_PAPER_DIR)
