# Submitted predictions — historical artifacts

[`littraceqa-test_OdeD.jsonl`](littraceqa-test_OdeD.jsonl) is the retained best submission artifact described in the [system paper](../paper/littraceqa_system.pdf). Its reported official overall score was **0.7649**. The team arrived at it using per-question source-PDF auditing and leaderboard-feedback attribution in addition to its automated pipeline; it is **not** evidence that a fresh unattended run achieves 0.7649.

The best fully automated reported run scored **0.5519**. For scorer provenance, see [`results/official_scores.csv`](../results/official_scores.csv), [`reports/scoring_and_fixes.md`](../reports/scoring_and_fixes.md), and the [reproducibility guide](../docs/REPRODUCIBILITY.md). Preserve this JSONL as a historical submission rather than overwriting it with a new experiment; write new predictions to the gitignored `preds/` directory.
