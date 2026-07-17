# Human-friendly entry point for reproducible experiment workflows.
# Run `just --list` to discover available recipes.

python := env_var_or_default("PYTHON", "python")
lattes_dir := "experiments/lattes"
baseline_dir := lattes_dir + "/baseline_001"
derived_dir := baseline_dir + "/derived"
analysis_dir := derived_dir + "/analysis"
figures_dir := derived_dir + "/figures"
expected_lattes := "expected/table-3a-lattes.csv"

# List available recipes.
default:
    @just --list

# Generate all Lattes baseline-derived CSV files.
lattes-analyze:
    {{python}} {{lattes_dir}}/analyze_lattes.py \
        {{baseline_dir}} \
        --output-dir {{analysis_dir}}

# Generate Lattes figures exclusively from baseline-derived CSV files.
lattes-figures: lattes-analyze
    {{python}} {{lattes_dir}}/generate_figures.py \
        {{analysis_dir}} \
        --output-dir {{figures_dir}}

# Run the complete deterministic Lattes analysis and figure workflow.
lattes-all: lattes-figures

# Execute the Lattes inspection notebook after generating its CSV inputs.
lattes-notebook: lattes-analyze
    jupyter nbconvert \
        --to notebook \
        --execute {{lattes_dir}}/analysis.ipynb \
        --output analysis.executed.ipynb \
        --output-dir {{derived_dir}}

# Verify Lattes-derived values against the published-table fixture.
lattes-verify: lattes-analyze
    {{python}} {{lattes_dir}}/analyze_lattes.py \
        {{baseline_dir}} \
        --output-dir {{analysis_dir}} \
        --expected {{expected_lattes}} \
        --verify

# Remove all generated Lattes outputs.
lattes-clean:
    rm -rf {{derived_dir}}
