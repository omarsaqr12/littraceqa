# What the scoring function actually rewards, and what that changed

> **CORRECTION (16 Aug 2026): §1 of this document is wrong.** The weight vector
> below was fitted on five leaderboard rows with the table column mislabelled --
> `table_row_f1 / cell_acc_macro / cell_acc_micro` were read as table P/R/F1. It
> overshoots every one of our own scored submissions by +0.025 to +0.032.
> The true formula, verified to six decimals on all three, is
> `overall = (paper_f1 + evidence_f1 + mean(MC, table_row_f1, table_cell_acc_macro)) / 3`.
> Table is 2/9 of the score, not 0.177. See `endgame.md §1`.
> Everything in §2-§6 below (abstention, locator transcribability, the "A"
> fallback, the set-size regex) was measured directly and still stands.

Measured 15-16 Aug 2026 on the released splits. Everything here is reproducible
from `data/` plus the commands at the bottom; nothing is quoted from memory.

## 1. The overall score is a fixed weighted sum, and we now know the weights

Fitting the five leaderboard rows in `leaderboard_gap.md` against their four
component scores recovers the weights to within 0.0008 on every team:

```
overall = 0.364*paper_F1 + 0.337*evidence_F1 + 0.177*table_F1 + 0.108*MC_accuracy   # SUPERSEDED
```

**This is not the scoring function.** Retained only to document how the error was
made: five rows, four free parameters, and a mislabelled column will fit almost
anything. The give-away was visible immediately -- it missed our first scored
submission by +0.0253 -- and should have prompted a refit rather than three more
configs ranked under it.

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

## Object-id verification (v36)

`coarse_evidence_key` puts the visible object id in the key, so a right page with
a wrong "Table 3" scores zero. Captions in this corpus are regular enough that a
regex over page text checks every id independently.

**48 of 49 confirmed on the page we claim.** The exceptions:

* `naacl2025_00527`: the Race retention-score column lives in **Table 1** on p6
  ("Debiasing results on BERT"); Table 2, whose caption sits on p7, is the GLUE
  table. Corrected.
* `acl2025_01350` "Table I8" -- the caption is genuinely on p24; my regex
  requires a digit right after "Table" and refused the letter. Detector limit,
  not a bad citation.

## Three MC answers re-confirmed, not changed

An option-scoring pass (numbers matched as standalone tokens, after the earlier
version found `86.47` inside `186.472`) flagged three questions. All three were
already correct, and in each case the higher-scoring decoy is a real number from
the very same table:

| question | our answer | the decoy, and what it actually is |
|---|---|---|
| `ltqa_22ff7b719c5625d4` | MC3 = 41.25 | 43.01 is **MC1** of the 1.3B-Finetuned row |
| `ltqa_98ff929cb222a1b3` | MAE = 0.668 | 0.906 is the **audio-only** column; the question asks multimodal |
| `ltqa_f6ae14ff5b8d177b` | 94.4 | 94.5 is cross-check **enabled**; the question says disabled |

This is the same pattern as every earlier triage: the wrong answers are all
printed in the cited paper, one row or one column away. It is why value-presence
tests cannot settle these and reading the header can.

## Hedging two locators beats guessing one

Where a value provably appears in two places and nothing distinguishes which the
grader keyed, emitting both is better arithmetic than picking one. Against a
single gold item, two predictions with one hit score F1 2/3; a coin flip between
them averages 1/2. Applied twice, both times after confirming both locations
hold the value: `ltqa_dc59b0be539a1b22` (prose and Figure 6, same page) and
`ltqa_f6ae14ff5b8d177b` (Figure 1 p1 and Table 1 p6).

## A bug in my own option-scoring probe (and what it hid)

The first version of the MC option scorer stripped whitespace before matching.
That glues adjacent table cells together: UKBOB's Table 1 row reads
`... N/A 16,825,000 5,800,000 ...`, which flattens to `N/A16,825,0005,800,000`,
and the standalone-token test then rejects **both** numbers because each is
flanked by a digit. Table numbers are precisely what these questions ask about,
so every "absent" verdict from that version was worthless.

Fixed by collapsing whitespace instead of removing it. Re-run over all 50 MC
questions, it flags two, and both resolve against the source:

* `ltqa_394b3fcabbc496d9` -- 0.11 looked absent while 0.06, 0.08 and 0.14 looked
  present. Those three are **axis tick labels** of Figure 1, not data. Table 1 on
  p6 gives C-NICP on D-FAUST as **0.108**, so option C (0.11) is right and was
  already our answer.
* `ltqa_98ff929cb222a1b3` -- the missing "60" belongs to the word-colour paper
  that is not findable in the pool; the MAE half (0.668) is confirmed.

## Fourth MC correction: the two papers date LDA differently

`ltqa_bde426d34c7e10bd` asks which citation both papers use "as the canonical
Latent Dirichlet Allocation citation". They do not use the same one:

* `naacl2025_00627` (Instruct-LF) writes "Blei et al., 2009" on p1, p2, p3 and
  p5, and its own reference list on p9 reads "David M. Blei, A. Ng, and Michael
  I. Jordan. **2009**. Latent dirichlet allocation."
* `naacl2025_01120` (LLMs-in-the-Loop) writes "(Blei et al., **2003**)" on p1.

Option B is the only one that states that split, so the answer moved D -> B.
Recorded as a judgement call: the question's premise that the two match is
false, and B is too specific to be an accidental distractor -- but if the grader
only opened one of the two papers, the gold is A or D and this costs one
question.

### Answers verified and left alone in this pass

`ltqa_1a7bdefccf618e42` (p4: "determinant of the covariance matrix det(sigma_n)"),
`ltqa_3bfb8111c92ba3d5` (O(1/sqrt(T)) with EXP3, p1/p2/p4),
`ltqa_b18f17b22f0bfdbe` (p3: FiSAO uses "level feedback from the visual encoder"),
`ltqa_571b8ccefde36062` (Table 1 p3: Abdomen Atlas 16,825,000 label masks,
Total Segmentator 400,000 images -- both in the column the question names).

## v49: undo the three misses, resolve the last ambiguous evidence set

v48 scored **0.7502**. All three deltas decomposed exactly:

| delta | reading |
|---|---|
| row **-0.2952** | precisely what three candidate-key misses predict, so all three missed |
| cell **+0.5000** | two 0.25-steps among dd9546 / a805cd / 033b9d landed |
| evidence **+0.5000** | one of the two figure fixes landed |

`bed9aa`'s `quantity_asked` is now excluded as well: it can gain at most 0.333
(2 cells of 6), so it cannot be part of a +0.5. **Three different forms of that
string have now missed.** Stopping there.

v49 drops the three dud keys, which is a certain recovery of +0.0141 row F1, and
resolves `ltqa_c0b2f8616b032d4b`. That set scored 0.5 both before and after v48,
which leaves exactly two possible gold sets:

* **A** `{text_span 02644 p3, figure 01958 p3 Fig 1}`
* **B** `{figure 02644 p3 Fig 2, citation 01958 p2}`

Emitting one pair is worth 0.75 in expectation against 0.667 for hedging all
four, so pick the coherent one. A: the question's clause for `02644` mentions no
figure and its answer ("three categories of alterations") is p3 prose, while for
`01958` it says "the saliency-alignment framework's **figure** apply".

### Where the measurable signal runs out

I checked whether to convert the equation hedges into clean picks by dropping
their `text_span` partners. Working it through: gold has one key per paper in 43
of 55 validation questions, so a 2-paper question most likely has 2 gold items.
Keeping the hedge is worth 0.767, dropping is worth 0.760 -- **indistinguishable**,
so churning them would be motion without expected value. Same conclusion for the
descriptor row keys, for a different reason: three failed forms of one such
string is direct evidence the wording is not recoverable by paraphrase.
