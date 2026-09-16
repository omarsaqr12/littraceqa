# Experiments

This directory holds **22 numbered experimental scripts and `run_ablation.py`**. They are research history rather than a maintained integration-test suite. Some configurations require downloaded data, model checkpoints, API keys or services that are not pinned in the repository. Running the scripts does not by itself reproduce the official hidden-test score.

Start with the [experiment-by-experiment index](../docs/EXPERIMENT_INDEX.md), then read the associated [research reports](../reports/README.md) for the measurement, control configuration, negative results and any later correction. The [reproducibility guide](../docs/REPRODUCIBILITY.md) explains which activities are offline and what external resources a new run requires. Avoid running a full sweep merely to inspect the repository.

When extending this work, record the exact data revision, seed, model and API versions, flags, error count and matched control for both comparison arms. Keep manually audited submissions separate from automated outputs.
