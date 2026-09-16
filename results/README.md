# Results and scorer records

This directory preserves **historical official-score records** and scripts for checking the arithmetic of *retained* components. It does **not** contain a newly rerun hidden-test evaluation or all private gold labels.

| File | What it is |
| --- | --- |
| [`evaluator_log.csv`](evaluator_log.csv) | Partial exported evaluator log; it is not a complete count of team submissions. |
| [`official_scores.csv`](official_scores.csv) | Curated scored-submission ledger, including reuploads and a row not present in the partial log export. |
| [`validate_table3.py`](validate_table3.py) | Checks the overall metric against retained component scores, allowing documented display rounding. |
| [`table3_validation.csv`](table3_validation.csv), [`table3_validation.json`](table3_validation.json) | Stored arithmetic-check outputs, not model predictions. |
| [`count_conventions.py`](count_conventions.py), [`convention_counts.json`](convention_counts.json) | Historical annotation-convention inspection and its recorded output. |
| [`check_manuscript.py`](check_manuscript.py) | Manuscript consistency checks; not a source of hidden-test gold labels. |

For a lightweight local arithmetic check, run `python3 results/validate_table3.py` from the root (it overwrites the two `table3_validation` outputs; use a disposable checkout to preserve the committed versions). Rows lacking component values are **not checkable**, even if their displayed official overall is retained. The documented fully automated score (0.5519) must not be conflated with the best submitted score (0.7649), which included manual PDF review and leaderboard-feedback attribution. See the [paper](../paper/littraceqa_system.pdf), [scoring analysis](../reports/scoring_and_fixes.md) and [reproducibility guide](../docs/REPRODUCIBILITY.md).
