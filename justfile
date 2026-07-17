# Human-friendly entry point for reproducible experiment workflows.
# Run `just --list` to discover available recipes.

python := env_var_or_default("PYTHON", "python")

lattes_dir := "experiments/lattes"
lattes_baseline := lattes_dir + "/baseline_001"
lattes_derived := lattes_baseline + "/derived"
lattes_analysis := lattes_derived + "/analysis"
lattes_figures := lattes_derived + "/figures"
expected_lattes := "expected/table-5-lattes.csv"

repoqa_dir := "experiments/repoqa"
