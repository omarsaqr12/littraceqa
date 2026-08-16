# What the scoring function actually rewards, and what that changed

Measured 15-16 Aug 2026 on the released splits. Everything here is reproducible
from `data/` plus the commands at the bottom; nothing is quoted from memory.

## 1. The overall score is a fixed weighted sum, and we now know the weights

Fitting the five leaderboard rows in `leaderboard_gap.md` against their four
component scores recovers the weights to within 0.0008 on every team:

```
overall = 0.364*paper_F1 + 0.337*evidence_F1 + 0.177*table_F1 + 0.108*MC_accuracy
```

| team | reported | reconstructed | error |
|---|---|---|---|
| ACF | 0.7698 | 0.7690 | -0.0008 |
| DKE | 0.7689 | 0.7690 | +0.0001 |
| Everest | 0.5768 | 0.5761 | -0.0007 |
| gabby | 0.4575 | 0.4569 | -0.0006 |
| orgtest | 0.0482 | 0.0481 | -0.0001 |

This settles the priority order. Paper and evidence carry **70.1%** of the score
between them; multiple choice, which is 50 of the 71 test questions, carries
**10.8%**. Effort should follow the weights, not the question counts.

## 2. Abstaining is never worth a point

`evaluate.prf` returns F1=0.0 for an empty prediction against non-empty gold,
and F1=0.0 for a wrong one. The only case where silence pays is empty gold, and
there is none: **all 55 validation questions have non-empty gold papers and
non-empty gold evidence.**

The pipeline was abstaining in three places -- a prompt instruction to return
`evidence=[]` when unsure, a confidence floor in `collect_evidence`, and a rule
that stripped `page` from arXiv-sourced PDFs. Together they left 29 of 71
questions in `test_v2_rerank.jsonl` with no evidence at all, a guaranteed zero
on 33.7% of the score.

The page-stripping rule was the least obvious and the most clearly wrong.
**Gold carries a page on 149/149 validation evidence items**, so the evaluator's
location field is never empty; emitting no page guarantees a mismatch where a
possibly-wrong page could at least land. For `text_span` it is worse still,
since page is that type's only locator and stripping it deletes the item.

## 3. Gold locators are transcribable, not inferable

| source_type | gold items | carry a page | carry an object id |
|---|---|---|---|
| table | 64 | 64 | 64 |
| text_span | 54 | 54 | **0** |
| figure | 18 | 18 | 18 |
| equation_algorithm | 7 | 7 | 7 |
| citation_context | 6 | 6 | 6 |

Both halves of the key are graded exactly, and both are printed in the PDF. So
`littraceqa/pdf/objects.py` enumerates the locators a PDF can support -- captions
with the page PyMuPDF found them on, numbered references, one `text_span` per
page -- and the reader returns an index into that list rather than generating a
page number. `text_span` needs only a correct page, since the evaluator sets its
object id to `""` unconditionally.

## 4. "A" was the worst possible fallback label

Validation gold multiple-choice labels: **A=2, B=17, C=11, D=11** (n=41). The
fallback in both `solve.py` and `build.py` was `sorted(options)[0]`, i.e. always
"A" -- correct 4.9% of the time against 25% for a blind guess, and emitted on 16
of 71 questions in the last test run.

It is now a uniform pick seeded on `query_id`. Uniform rather than "always B":
B wins on 41 samples, but that is a property of one small annotated split.
A retrieval-only validation run now scores **MC 0.244**, which is the 25% a
uniform guess should earn and confirms the fallback behaves as intended.

## 5. Measured effects

Validation, 55 questions, official evaluator.

| config | paper F1 | evidence F1 | MC | table row F1 |
|---|---|---|---|---|
| no rerank (old default) | 0.410 | — | — | — |
| **+ cross-encoder rerank** | **0.490** | — | — | — |
| full pipeline, reader on | 0.490 | 0.277 | 0.390 | 0.528 |

Split by task family, which matters because the test split is the named-paper
regime and validation is mostly the cluster regime:

| family | n | paper F1 | evidence F1 |
|---|---|---|---|
| `hidden_source_single_paper` (test-like) | 26 | **0.846** | **0.538** |
| `multi_paper` (cluster regime) | 29 | 0.171 | 0.043 |

Conditioning on whether we retrieved any gold paper:

| | n | evidence F1 | MC |
|---|---|---|---|
| paper overlaps gold | 35 | 0.436 | 0.600 |
| paper missed entirely | 20 | 0.000 | 0.062 |

MC lands far below random when the paper is wrong: the reader answers
confidently from the wrong paper. Nothing downstream is recoverable without
paper selection.

### Two things that turned out not to matter

* **Cluster expansion was inert, not harmful.** The `--no-expansion` flag was
  inverted in `run.py`, so expansion ran by default against
  `PipelineConfig.use_expansion=False`. It changed nothing: `select_papers`
  builds `seeds = ranked[:size]`, which already has `size` members, so
  `ClusterExpander.expand(seeds, target_size=size)` returns immediately. Turning
  it off produced byte-identical predictions. The flag is fixed because the
  latent bug would bite the moment the seeding changed, not because it cost
  points.
* **Pinning unambiguous title matches loses points.** q_004's "DynaPipe"
  matches exactly one of 27,487 titles at score 1.0 and still lost its slot to
  the reranker. Forcing it to rank 0 costs paper F1 0.490 -> 0.465 overall and
  0.846 -> 0.808 on the test-like family, because `extract_nicknames` returns
  every named artefact and most are datasets or baselines, not the subject of
  the question. Disabled by default in `PipelineConfig`.
* **Citation numbers are not worth special handling.** They are 5 of the 8
  remaining evidence failures on test-like questions, but **0 of 71 test
  questions mention a numbered reference**.

## 6. Set sizing, and the one regex that mattered

`_COUNT_BEFORE` spelled a word as `\w+`, which does not match a hyphen. ML papers
are described almost entirely in hyphenated compounds, so "the two ICCV 2025
alignment-related adversarial papers" spent its four-word budget on
"alignment" + "related" and read as a single-paper question.

| | before | after |
|---|---|---|
| test questions with a detected explicit count | 10 | 20 |
| test predicted set sizes | {1: 61, 2: 10} | {1: 44, 2: 25, 3: 2} |
| test papers per question | 1.14 | **1.408** |
| validation exact-size accuracy | 27/55 | 27/55 (unchanged) |

Validation cannot measure this: its gold sets are 1 or 4, so predicting 2 is
never exactly right. It confirms no regression, nothing more.

The marginal rule that justifies returning a second paper: on a 2-paper gold set
where we currently return one correct paper, F1 = 0.667, and adding a second
paper with probability `p` of being gold gives `E[F1] = 0.5 + 0.5p`. That beats
0.667 whenever **p > 1/3**.

## 7. Reproduce

```bash
.venv/bin/python run.py --split validation --no-read --out preds/val_retrieval.jsonl
.venv/bin/python run.py --split validation --mc-samples 1 --out preds/val_full.jsonl
.venv/bin/python scripts/validate_submission.py --input data/test.jsonl --pred preds/test_v3.jsonl
```
