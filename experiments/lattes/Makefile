PYTHON ?= python
EXPERIMENT_DIR ?= baseline_001
DERIVED_DIR := $(EXPERIMENT_DIR)/derived
ANALYSIS_DIR := $(DERIVED_DIR)/analysis
FIGURES_DIR := $(DERIVED_DIR)/figures
EXPECTED ?= ../../expected/table-3a-lattes.csv

.PHONY: all analyze figures notebook verify clean

all: analyze figures

analyze:
	$(PYTHON) analyze_lattes.py $(EXPERIMENT_DIR) --output-dir $(ANALYSIS_DIR)

figures: analyze
	$(PYTHON) generate_figures.py $(ANALYSIS_DIR) --output-dir $(FIGURES_DIR)

notebook: analyze
	jupyter nbconvert --to notebook --execute analysis.ipynb \
		--output analysis.executed.ipynb --output-dir $(DERIVED_DIR)

verify: analyze
	$(PYTHON) analyze_lattes.py $(EXPERIMENT_DIR) \
		--output-dir $(ANALYSIS_DIR) --expected $(EXPECTED) --verify

clean:
	rm -rf $(DERIVED_DIR)
