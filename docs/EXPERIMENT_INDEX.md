# Experiment navigation index

The numbered scripts in [`exp/`](../exp/) are a historical *research notebook in code*: the team tested hypotheses, recorded both successful and unsuccessful approaches, and later corrected some comparisons. This index helps reviewers locate the executable starting point and its interpretation. It is **not** a claim that all 23 scripts currently execute from a fresh checkout or that every printed metric is a matched-control result. Read the reports and the [reproducibility guide](REPRODUCIBILITY.md) before rerunning a study.

| Script | Investigation |
| --- | --- |
| [`01_title_mangling.py`](../exp/01_title_mangling.py) | Recovering mangled paper titles |
| [`02_lexical_recall.py`](../exp/02_lexical_recall.py) | Lexical candidate recall |
| [`03_hybrid_recall.py`](../exp/03_hybrid_recall.py) | Hybrid retrieval |
| [`04_set_size_sweep.py`](../exp/04_set_size_sweep.py) | Predicting/choosing paper-set size |
| [`05_submission_shape.py`](../exp/05_submission_shape.py) | Submission schema and shape |
| [`06_expansion_diagnostic.py`](../exp/06_expansion_diagnostic.py) | Whether embedding-neighbor expansion retrieves missing papers |
| [`07_mention_anchored.py`](../exp/07_mention_anchored.py) | Mention-anchored paper selection |
| [`08_rerank.py`](../exp/08_rerank.py) | Cross-encoder reranking |
| [`09_caption_pages.py`](../exp/09_caption_pages.py) | Caption and page evidence |
| [`10_page_offset_audit.py`](../exp/10_page_offset_audit.py) | PDF page offset alignment |
| [`11_gold_null_cells.py`](../exp/11_gold_null_cells.py) | Null-cell conventions in gold tables |
| [`12_identify_match.py`](../exp/12_identify_match.py) | Generating and matching paper identities |
| [`13_llm_select.py`](../exp/13_llm_select.py) | LLM selection from a candidate shortlist |
| [`14_visual_table.py`](../exp/14_visual_table.py) | Reading table cells from rendered pages |
| [`15_mention_verify.py`](../exp/15_mention_verify.py) | Checking claimed paper mentions |
| [`16_candidate_misses.py`](../exp/16_candidate_misses.py) | Diagnosing failures to generate the right paper candidate |
| [`17_local_selector.py`](../exp/17_local_selector.py) | Locally served paper selector |
| [`18_free_selectors.py`](../exp/18_free_selectors.py) | Hosted/free selector comparison and rate-limit sensitivity |
| [`19_gemini37_subset.py`](../exp/19_gemini37_subset.py) | Model/subset comparison |
| [`20_table_schema_shape.py`](../exp/20_table_schema_shape.py) | Table schema and row shape |
| [`21_shortlist_recall.py`](../exp/21_shortlist_recall.py) | Shortlist coverage ceiling |
| [`22_row_key_extraction.py`](../exp/22_row_key_extraction.py) | Extracting exact table row keys |
| [`run_ablation.py`](../exp/run_ablation.py) | Configurable ablation runner |

## Interpret results using their corrections

- [Paper selection](../reports/paper_selection.md) and [retrieval findings](../reports/retrieval_findings.md) explain which candidate and reranking changes the team measured and rejected.
- [Table-stage notes](../reports/table_stage.md) and [scoring/fixes](../reports/scoring_and_fixes.md) explain evaluator-specific evidence and answer format behavior.
- [Free selectors and evidence](../reports/free_selectors_and_evidence.md) retracts an earlier free-selector conclusion after discovering a rate-limit artifact. Do not copy the old model ordering out of context.
- [Local reader](../reports/local_reader.md), [leaderboard gap](../reports/leaderboard_gap.md), and [endgame](../reports/endgame.md) record later experiments, scoring mechanics, and limitations.
- [`HYPOTHESES.md`](../HYPOTHESES.md) tracks attempted and refuted directions. A negative result or a superseded result is part of the work, not clutter to delete.

For any performance comparison, identify the exact split, candidate pool, flags, API errors, model revision, matched control, and whether per-question human auditing or leaderboard feedback intervened. The best reported submitted score (0.7649) is **not** the fully automated result (0.5519).
