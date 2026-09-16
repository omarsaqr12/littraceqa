# Research reports — read findings with their corrections

The reports are **historical experiment records**, not one synchronized performance summary. They preserve negative results, evaluator discoveries and retracted interpretations. Start with the [system paper](../paper/littraceqa_system.pdf), [root overview](../README.md), and [experiment index](../docs/EXPERIMENT_INDEX.md). For any metric, check the split, flags, API error counters, matching control and whether manual auditing or leaderboard feedback intervened.

| Question | Reports to read |
| --- | --- |
| How are official metrics combined? | [`scoring_and_fixes.md`](scoring_and_fixes.md), [`endgame.md`](endgame.md) |
| Which papers were retrieved and selected? | [`paper_selection.md`](paper_selection.md), [`retrieval_findings.md`](retrieval_findings.md) |
| What worked for evidence and table answers? | [`table_stage.md`](table_stage.md), [`e4_e6_measurements.md`](e4_e6_measurements.md) |
| What happened with other selectors and reader models? | [`free_selectors_and_evidence.md`](free_selectors_and_evidence.md), [`local_reader.md`](local_reader.md) |
| Why does the automated score differ from the best submission? | [`leaderboard_gap.md`](leaderboard_gap.md), [`scoring_and_fixes.md`](scoring_and_fixes.md) |
| How was the camera-ready manuscript reviewed? | [`camera_ready_audit.md`](camera_ready_audit.md), [`camera_ready_validation.md`](camera_ready_validation.md), [`camera_ready_changelog.md`](camera_ready_changelog.md), [`camera_ready_style_changelog.md`](camera_ready_style_changelog.md) |

**Important correction:** an early free-selector conclusion was retracted after rate limiting corrupted a comparison. See [`free_selectors_and_evidence.md`](free_selectors_and_evidence.md); do not quote the old ranking without the correction. The official score log itself is partial, and arithmetic validation of retained components is not independent scoring of the hidden-test submission. For levels of reproducibility, read [`docs/REPRODUCIBILITY.md`](../docs/REPRODUCIBILITY.md).
