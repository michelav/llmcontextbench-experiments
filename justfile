# Human-friendly entry point for reproducible experiment workflows.
# Run `just --list` to discover available recipes.

python := env_var_or_default("PYTHON", "python")

lattes_dir := "experiments/lattes"
lattes_baseline := lattes_dir + "/baseline_001"
lattes_derived := lattes_baseline + "/derived"
lattes_analysis := lattes_derived + "/analysis"
lattes_figures := lattes_derived + "/figures"

repoqa_dir := "experiments/repoqa"
repoqa_baseline := repoqa_dir + "/baseline-01"
repoqa_derived := repoqa_baseline + "/derived"
repoqa_analysis := repoqa_derived + "/analysis"

# List available recipes.
default:
    @just --list

# Generate all Lattes baseline-derived CSV files, including Tables 5, 6, and 7.
lattes-analyze:
    {{python}} {{lattes_dir}}/analyze_lattes.py \
        {{lattes_baseline}} \
        --output-dir {{lattes_analysis}}

# Generate paper Figure 3a, Figure 3b, and the combined Figure 3.
lattes-figures: lattes-analyze
    {{python}} {{lattes_dir}}/generate_figures.py \
        {{lattes_analysis}} \
        --output-dir {{lattes_figures}}

# Run the complete deterministic Lattes analysis and figure workflow.
lattes-all: lattes-figures

# Execute the Lattes inspection notebook after generating its CSV inputs.
lattes-notebook: lattes-analyze
    jupyter nbconvert \
        --to notebook \
        --execute {{lattes_dir}}/analysis.ipynb \
        --output analysis.executed.ipynb \
        --output-dir {{lattes_derived}}

# Remove all generated Lattes outputs.
lattes-clean:
    rm -rf {{lattes_derived}}

# Generate analysis-ready RepoQA CSVs from the complete committed baseline.
repoqa-analyze:
    {{python}} {{repoqa_dir}}/derive_repoqa.py \
        {{repoqa_baseline}} \
        --output-dir {{repoqa_analysis}}

# Remove generated RepoQA analysis outputs.
repoqa-clean:
    rm -rf {{repoqa_derived}}

# Generate the currently supported outputs for both experiments.
all: lattes-all repoqa-analyze

# Remove generated outputs from both experiments.
clean: lattes-clean repoqa-clean
