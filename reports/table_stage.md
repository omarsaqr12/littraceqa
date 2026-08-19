# E7 — reading the table instead of a summary of it

Validation, 55 questions (11 with a table answer), official evaluator.

## Result: real but small

Measured on top of `--llm-select`, every other component byte-identical:

| config | paper | evid | MC | row F1 | cell acc | **overall** |
|---|---|---|---|---|---|---|
| control | 0.4901 | 0.2724 | 0.4878 | 0.5280 | 0.2098 | 0.3904 |
| +llm-select | 0.5837 | 0.3127 | 0.5854 | 0.5338 | 0.1929 | 0.4446 |
| **+visual-table** | 0.5837 | 0.3127 | 0.5854 | 0.5338 | **0.2384** | **0.4497** |

Cell accuracy **+0.0455**, overall **+0.0051**.

E7's success bar was row F1 ≥ 0.65 **and** cell accuracy ≥ 0.45. Neither is met.
It clears the kill threshold (cell ≥ 0.20) and is kept, but +0.0051 is an order of
magnitude below the +0.05 to +0.09 the endgame plan projected for a table rebuild.
This is a partial result and should not be described as the rebuild that plan asked for.

## What worked

`solve_table` fills the schema from `format_evidence()` — a one-line-per-paper digest of
the single answer string the reader produced for a different question. The values are
simply not in it. Rendering the page the table is printed on at 2× and asking for the
cells puts them in front of the model.

Verified directly on q_028: returns TCM **2.05** and sCT **2.06**, which is gold, where
the digest path returned 2.45 and 2.51.

## Two mistakes of mine, both caught before shipping

**The first version replaced the whole stage**, letting the image choose rows as well as
cells:

```
row F1    0.5280 -> 0.4591   (-0.0689)
cell acc  0.0682 -> 0.1591   (+0.0909)
```

Cell accuracy more than doubled and row F1 fell, and the row losses were entirely
questions the existing logic already gets right — q_027 fell 1.00 → 0.00 and q_023
0.31 → 0.00, both row-key columns served by the paper-title path. Rows and cells are
separable problems and the existing code is better at the first. `fill_cells` now keeps
the rows it is given and re-keys the model's reply against them, so the visual pass can
add, drop or rename nothing; it only supplies values.

**The cells-only measurement was itself confounded.** `exp/14` filled rows taken from
`val_control` (old paper selection) using readings from `val_llmsel` (new selection), so
the two halves of the comparison disagreed about which papers were involved. It reported
+0.0227 cell accuracy. The correct end-to-end run reports **+0.0455** — the flawed
version understated the effect by half.

This is the second time in this project a comparison was run with one arm taken from a
different configuration. The rule that prevents it: **both arms of an A/B must come from
runs made in the same session with the same flags**, and quoting a number from a report
is not a substitute for running the arm.

## Why it is still only 0.24

The remaining failures are not reading failures. On q_030 the four gold rows (MoST, PMA,
PointLoRA, RISurConv) carry ModelNet40 accuracies from **four different papers**, and we
render pages from the one or two papers selected. Three of the four cells are not in any
image we sent, so no amount of visual quality recovers them.

Table accuracy is therefore gated by paper selection in the same way evidence and MC
already are. Paper F1 is 0.5837 against the leaders' 0.99, and until that closes, the
multi-paper table questions cannot be filled from pages we never fetched.

That reframes the remaining table headroom: it is not mostly a table problem.

---

# E5 — the marginal-add rule does not hold for evidence

Validation, same pipeline, one change at a time.

| config | evidence F1 | MC | cell acc | ev/question | overall |
|---|---|---|---|---|---|
| 2 papers | 0.3127 | 0.5854 | 0.2384 | 1.16 | 0.4497 |
| 3 papers + padding prompt | 0.3084 | 0.5366 | 0.2838 | 1.45 | 0.4478 |
| **3 papers, prompt reverted** | **0.3197** | 0.5854 | 0.2611 | 1.25 | **0.4545** |

Isolated: **`--max-papers 3` is worth +0.0048; the padding prompt is worth −0.0066.**

## The negative result

We emit 64 evidence items against gold's 130 — 49%, a deficit of 66 across 55
questions. Evidence F1 is 0.3127, so the marginal-add rule says any location with
better than a `F1/2 = 0.156` chance of being gold raises expected F1. The reader
prompt was telling it the opposite ("Usually exactly one. Do not pad the list"),
so asking for 2-3 locations looked like free upside.

It is not. Padding moved recall +0.032 and precision −0.028, netting **−0.0043**
on evidence F1. The reader's second and third choices are worse than a one-in-six
guess, so they sit below the threshold the rule requires.

The rule is arithmetically correct and was applied to a population it does not
describe. `p > F1/2` is a statement about *a candidate whose probability you
know*; the reader's ranked guesses are not calibrated, and its tail is much worse
than its head. Establish that added items clear the bar before invoking the rule
— it licenses padding only when padding is with something better than noise.

## A side effect worth recording

Padding also cost MC 0.5854 → 0.5366. The extra locations enter
`format_evidence()`, which feeds the multiple-choice vote, so diluting evidence
quality degrades an answer component that was not the target. Changes to the
evidence stage are not local to evidence.

## Why the third paper helps

`--max-papers 3` lifts cell accuracy 0.2384 → 0.2611 and evidence F1 0.3127 →
0.3197 with MC unchanged. This is the q_030 mechanism from the other direction:
multi-paper table rows carry values from papers we had not fetched, and fetching
one more makes one more row fillable. Consistent with table accuracy being gated
by paper coverage rather than by table reading.

---

# F2 — why table collapses from validation to test

Test is easier than validation on paper, evidence and MC, and 2-3x worse on both
table metrics. That is a signature, not a difficulty gradient, so it was worth
chasing.

## First hypothesis: the paper-title path stops firing. True, and not the cause.

The free win (row values = the pool's `title` verbatim) required the table to
have exactly **one** column. Schema survey (`exp/20`):

| | validation | test |
|---|---|---|
| single-column tables | 3/11 | **0/21** |
| paper-title path fires | 18% | **0%** |
| title-ish key **with** extra columns | 0% | **19%** |

No test table has one column -- 8 have two, 13 have three -- so four test
questions keying on `paper` were handing their row keys to the model instead of
pinning the pool title. Generalised the path to fire on any title-ish row key,
filling the remaining columns as cells.

**Measured effect: nearly nothing.**

```
v9  (before)  title-key rows exactly matching a pool title:  9/10
v12 (after)   title-key rows exactly matching a pool title:  9/9
```

The model was already emitting exact pool titles. One row changed. The fix is
still right in principle -- it makes exactness structural rather than dependent
on the model paraphrasing correctly -- but it is not worth the +0.046 the schema
difference suggested, and it does not explain the collapse.

## Actual cause: the two splits ask for different kinds of row key

Validation gold row-key values are **entity names**, short and canonical and
present verbatim in the question:

```
q_028  Method      TCM, sCT, ECM-XL, IMM
q_030  Method      MoST, PMA, PointLoRA, RISurConv
q_052  Benchmarks  SUN RGB-D, ARKitScenes, Hypersim, Objectron
q_027  Author      Nikos Athanasiou
```

Test row-key **columns** are descriptors: `quantity`, `adaptation_setting`,
`method_metric`, `setting`, `attribute`, `cited_work`. Their values are phrases
-- "number of optimization iterations for NeRF editing", "contrastive-learning
pre-training learning rate" -- and `row_key_value` grades them by exact string
match after normalisation.

Reproducing an entity name is a lookup. Reproducing a descriptive phrase someone
else wrote is not, and no amount of reading the paper makes the wording
predictable. 8 of 21 test tables key on a descriptor; 11 of 11 validation tables
key on an entity or a title.

This bounds what the table component can return on test, and it means validation
cannot be used to tune it: the mechanism that fails on test does not occur on
validation at all.

The remaining idea (H10 -- extract row keys verbatim from the question's noun
phrases rather than letting the model compose them) targets exactly these 8
questions and is untestable on validation for the same reason. It is recorded,
not shipped.

---

## Row keys from a dedicated question-only call (H10/H20): verified on validation, ~zero on test

Row F1 is a set F1 over row-key strings graded by exact match after
`normalize_text`. The combined table call receives the papers' evidence alongside
the question and drifts to the *papers'* wording, but the grader who wrote gold
also wrote the question, so question wording is the better prior. 44% of gold row
keys appear verbatim in the question text.

`--row-key-extract` splits the stage: one call decides row keys from the question
alone, then `_fill_remaining` fills cells against fixed keys.

**Ungated it loses 0.129.** On a discovery question ("Which CVPR 2025 papers cite
UniAD ...") the question does not name the rows, and the extractor either returns
nothing or fabricates an entity — it replaced a correct author, which the combined
call had read out of a reference list, with an invented name.

The fix is a grounding guard: every extracted key must appear in the question
after stripping a trailing parenthetical. That separates enumerated questions from
discovery ones exactly. Guarded, on the 10 single-row-key validation table
questions (`exp/22`):

| question | key column | combined call | guarded extractor | route |
|---|---|---|---|---|
| q_028 | Method | 0.750 | **1.000** | extractor |
| q_029 | Method | 0.750 | **1.000** | extractor |
| q_027 | Author | 1.000 | 1.000 | fallback (not grounded) |
| q_020, q_023 | Paper Title | 0.222 / 0.571 | unchanged | title pin |
| q_030, q_052, q_054, q_056, q_022 | — | — | unchanged | — |
| **mean** | | **0.6044** | **0.6544** | **+0.0500** |

Both wins are the qualifier rule: gold is `ECM-XL` where the question wrote
`ECM-XL (100k iterations)`, and `ECM-XL (102.4M)` where it wrote
`ECM-XL (with 102.4M training budget)`. No question regressed.

### On test it changes five questions, and two of them look worse

Routing over the 21 test table questions: **4 title-pin, 14 grounded, 3 fallback**.
But for 11 of the 14 grounded the extracted keys are *identical* to what already
ships — those questions were already question-derived. `test_v16` differs from v9
on 5 row-key sets:

| key column | v9 | v16 | judgement |
|---|---|---|---|
| `dataset` | `cosql`, `sparc` | `cosql validation set`, `sparc validation set` | **longer, likely worse** |
| `attribute` | `number of annotators` | `number of annotators used` | **longer, likely worse** |
| `quantity` | `plotted ratio for the lowest problem-difficulty value` | `lowest problem-difficulty value` | shorter, plausibly better |
| `paper` | clean `cot-icl lab: ...` | mangled `c o t - icl lab: ...` | verbatim pool title, plausibly better |
| `paper` | 2 keys | 1 key | worse, and caused by selector variance not this flag |

**The validation lesson and the test behaviour disagree.** Validation taught that
gold *shortens* what the question spells out; on test, copying the question
verbatim made two keys *longer*, because the question really does say "validation
sets". "Question-verbatim" and "shortest form" are different rules that happened
to coincide on validation, and nothing available locally says which one gold used.

Two further reasons `test_v16` is not a clean read of this flag:

* **It is not single-variable.** 4 of 71 paper sets differ from v9 purely from
  selector nondeterminism, one of which cost a table row.
* **v9 predates the generalised title pin** (added in v12, which scored 0.5413
  against v9's 0.5519). Current code therefore differs from v9 on the 4
  `paper`-keyed questions as well.

**Conclusion: the mechanism is real and measured, and its test footprint is not.**
Expected overall movement is ~±0.006, comfortably inside the ±0.011 run-to-run
band. Under this repo's own rule — do not ship on a validation delta below 0.02 —
`--row-key-extract` does not qualify on its own, and it is kept behind a flag,
default off.
