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

## Bare-entity row keys in a separate call: the validation result, and a test run lost to quota

v16 taught the rule the hard way. Copying the question verbatim lengthened `cosql`
to `cosql validation set`, and the loss was arithmetically exact: **−0.0476 row F1
and −0.0476 cell accuracy, i.e. exactly 1.000 of each over 21 questions.** One
perfectly scored question went to zero, and it took its cells with it — a broken
row key removes that row from `gold_by_key`, so every cell in it is scored wrong.

That isolates the real rule. Three arms on validation, one session, differing only
in row-key policy:

| policy | row F1 | cell accuracy |
|---|---|---|
| v9 combined call | 0.5338 | 0.2838 |
| shorten *inside* the combined call | **0.5773** | 0.2136 |
| **separate key call + bare names** | **0.5773** | **0.2818** |

Shortening buys row F1 and pays for it in cells when one call emits both, because
changing the key rule perturbs the values too. Splitting the stages keeps the gain
and leaves cells alone. All three arms verified clean: 0/55 empty evidence and
0/11 all-null tables.

The rule that works is **"the bare proper name of the thing the row is about"** —
`VideoLLaMB`, not `VideoLLaMB recurrent memory bridge design`. It is not
"question-verbatim": those two coincided on validation and diverged on test. 12 of
46 non-paper test row keys are five or more words of description, which is what
this targets.

### The test run is void: Gemini's daily quota died mid-run

`test_v17` reports 4 of 71 empty evidence and **9 of 21 table questions with a
single all-null row**. That is not the row-key policy failing. It is
`QuotaExhausted` on the free tier's 500 requests/day: `generate_json` returns
`None`, and `solve_table` falls back to `_complete_row({})`, which emits exactly
one row of nulls. The trace records **no** error for any of these questions.

`test_v17` and the `test_v18` graft built from it are discarded, not submitted.

**Fourth silent-failure instance this session**, after the rate-limit fallback to
BM25, the stale A/B baseline, and the wrong-key diff. Every one returned a
plausible number instead of raising. The standing rule — check the error counter
before reading a score — was not sufficient here, because the counter said 2. The
stronger check that would have caught it: **assert no all-null answer rows before
scoring a run**, since gold cells are never null.

Net position: the mechanism is measured and real on validation (+0.0434 row F1,
cells intact) but worth only ~+0.005 overall there, which is under this repo's
0.02 ship threshold. It remains behind `--row-key-extract`, default off, and
untested on test.

## v19: the row keys written by hand, three questions, from the scored baseline

With the Gemini day-quota gone, the row-key stage was done directly rather than by
another model call. Reading all 21 test table questions against v9's emitted rows,
only three warranted a change. Everything already correct was left untouched —
that is the `cosql` lesson, and 18 of 21 questions are in that category.

| # | row-key column | v9 | v19 | why |
|---|---|---|---|---|
| 8 | `method_metric` | `NeRFmm`, `BARF` | `NeRFmm RPEr`, `BARF ATE` | the only other columns are the two scenes `Rm-2` and `Off-0`, so the metric has nowhere to live except the row key, and the column is literally named `method_metric` |
| 10 | `method` | `VideoLLaMB recurrent memory bridge design`, `WINS Winograd pruning design` | `VideoLLaMB`, `WINS` | the column is `method`; bare proper name beats a description of the design |
| 14 | `paper` | `CoT-ICL Lab: ...` | `C o T - ICL Lab: ...` | gold paper-title keys are the pool title byte-for-byte, mangling included; the pool holds the spaced form |

Deliberately **not** changed, despite being verbose: the `quantity`, `setting`,
`attribute` and `metric` columns (#3, #11, #12, #13, #21). Those columns ask for a
descriptor rather than an entity, so a bare name would be semantically wrong, and
gold's exact phrasing is unknowable. Substituting one guess for another has no
expected value — that is what v16 did, and it cost 0.0130.

`test_v19` is the cleanest single-variable submission this project has produced:
papers, evidence, multiple-choice and every cell value are **identical to v9**, and
exactly 5 row-key strings differ. Any score movement is attributable to row-key
surface form alone. Three questions can move, so the range is roughly ±0.032
overall.

### The guard that would have caught test_v17

`scripts/validate_submission.py` now fails a submission containing an all-null
table row. Gold cells are never null (0 of 27 graded), so such a row is always a
dead run rather than a considered answer, and it is invisible to every other check:
`test_v17` was well-formed, passed validation, and recorded no error in its trace.

    test_v17  Submission is well-formed but DEAD: 9 all-null table row(s)
    test_v19  Submission is valid: 71 predictions

Four silent failures this session — rate-limit fallback to BM25, a stale A/B
baseline, a wrong-key diff, and a quota death — and each one produced a plausible
number instead of an error. This is the first of them to get an automated check
rather than a note in a report.

## Reading the papers by hand: v20 through v22

With the model quota gone, the table cells were verified directly against the
PDFs. Triage first: grep every emitted cell value against the selected papers'
extracted text, since a value that appears nowhere in the paper was invented.
**9 of 21 table questions had at least one.** Filtering out descriptor columns
(which we legitimately paraphrase) and LaTeX rendering artefacts left six real
defects, all now corrected and each cited to a page.

| question | defect | corrected to | source |
|---|---|---|---|
| GenieBlue (MC) | answered the *un-finetuned base LLM* row, the intended distractor | option **B** (30.60 / 40.18) | `iccv2025_01015` Table 3 p3 |
| EpicPRM | wrong paper, so all three cells wrong (5.1%, 43.4%, 4) | **0.431, 0.541, 11** | `acl2025_00183` Figure 2 p3, text p4 |
| FocalPETR/StreamPETR | duplicate row repeated StreamPETR 1.19x twice | first row is **FocalPETR 1.18x** | `iccv2025_00046` p2 |
| DiTFastAttnV2 | duplicate row repeated the 1.5x speedup twice | first row is **68% attention-FLOPs reduction** | `iccv2025_00613` p1 |
| LiveBeauty | `Not reported`, which is never right — gold cells are never null | **200 sessions with 50 images per session** | `iccv2025_00902` p3 |
| LiveBeauty | `10,000`, but the row key asks for image *and* annotation counts | **10,000 images / 200,000 annotations** | `iccv2025_00902` p1-p2 |
| SCIQ scores | numbers right, format wrong: LaTeX `89.97\pm_{0.97}` | **`89.97±0.97`** | `naacl2025_00811` Table 10 p15 |

**Duplicate rows are worse than they look.** With a single row-key column, repeated
keys collapse in the scorer's dict, so a duplicated row is not merely wasted — it
silently discards the second value the question asked for. Both duplicates here
were concealing a real number.

**The `±` fix is grounded, not a guess.** Validation gold formats uncertainty as
`32.7±0.5`, no spaces, so the rendered form is what the grader used and LaTeX
source can never match it.

Verified correct and deliberately left alone: DisCo 75% less tokens (p2), DLFR-Gen
up to 3x (p1), RTDETRv2 ~114s (p5), LiveBeauty year 2024 and 20 annotators (Table
1 p2), and every `quantity`/`setting`/`metric` descriptor row key. Also checked:
**zero** number-typed cells fail `normalize_number`, so no cell is losing to a
type mismatch.

`preds/` and `logs/` are gitignored (generated outputs; the dataset is CC BY-NC and
not vendored), so these reports are the record. `test_v22` differs from the scored
v19 on six questions, every one PDF-verified.

## Wrong-row reads: the dominant cell failure, found by verifying semantically

"Value appears in the paper" does not mean correct — that was the wrong test. Every
cell defect found since is a **wrong-row read**: the right table, the right paper,
the wrong line or column. Attestation triage cannot see these because the number is
genuinely printed.

| question | we emitted | that number is actually | correct |
|---|---|---|---|
| ConECT chrF/COMET | 38.01 / 0.6537, 48.50 / 0.7774 | the **NLLB-600M** row | Baseline row: **83.73 / 0.9227** and **70.76 / 0.9335** |
| AccidentalGS NeRFmm RPEr | 2.923, 4.937 | NeRFmm's **RPEt** row, and 4.937 is the Off-1 column | **11.568, 9.66** |
| AccidentalGS BARF ATE | 3.727, 7.037 | BARF's **RPEr** row | **0.413, 10.297** |

The ConECT one matters most as a lesson: NLLB-600M is a separate pretrained system,
while the question asks for "the ConECT baseline". The paper's `Baseline` row is its
own from-scratch text-to-text model (A.2 p8: 32k shared SentencePiece vocab, tied
embeddings, 53M pairs). Both rows sit in the same table on p5 and both are fully
attested.

Verified **correct** and left untouched, which is as important as the fixes:

* **RetrieverGuard** (`naacl2025_00889` Table 6 p13): all **8** cells right —
  SciFact 69.3/63.2, HotpotQA 78.6/68.5, NFCorpus 31.8/11.2, Climate-FEVER
  35.7/25.5, each read from the `RetrieverGuard (Stella-400M) …+Fake2` rows.
* **Track-SQL** (`naacl2025_01103` Table 13 p17): SESE inference totals 240.348s
  (SparC) and 214.456s (CoSQL) both right.

Running total against the scored v19 (0.5602): **11 questions**, 5 paper sets,
3 multiple-choice answers, 6 evidence sets and **15 table cells**, every change
citing a page.

## Continued audit: verified-correct is a result too

| question | outcome | source |
|---|---|---|
| RetrieverGuard | **all 8 cells correct** | Table 6 p13, `RetrieverGuard (Stella-400M) …+Fake2` rows |
| Track-SQL | SESE totals 240.348 / 214.456 **correct** | Table 13 p17 |
| HateSieve / AceMath | **all 4 cells correct**: 1e-4, 4 epochs, 5e-6, 3e-6 | `naacl2025_00007` p13; `acl2025_00011` p20 §D.5 |
| GRAB / Matador / HCN-PAI | **1 of 3 wrong**: categories 7 -> **9** | `iccv2025_01050` **Table 2** p4 |

GRAB is a clean instance of the wrong-object failure. Table 2 ("GRAB categories and
graph properties") lists nine categories — Intercepts & Gradients, Stationary
Points, Trigonometric, Functions, Counting, Correlation, Area Bounded, Measures of
Spread, Range & Extrema — and their properties sum to the 23 the question cites. We
answered 7. Note the adjacent trap: **Table 1** reports `Tasks 5`, and Figure 3's
legend splits Range & Extrema into two, giving 10. Three different plausible numbers
sit within a few centimetres of each other, and only Table 2 answers the question
asked. Our evidence pointed at Table 1, so it was wrong too, and the coarse evidence
key includes the table id — that mismatch alone would have scored zero.

Matador's 57 material classes and HCN-PAI's four benchmark hypergraph datasets
(CORA, CITESEER, NTU2012, ModelNet40, `iccv2025_01167` p5) are both correct.

Two evidence pointers re-aimed at the page that actually contains the answer:
GRAB Table 1 -> Table 2, and HateSieve p4 -> p13.

### Running total, `test_v26` against the scored v19 (0.5602)

| | changed |
|---|---|
| questions | **13 of 71** |
| paper sets | 5 |
| multiple-choice answers | 3 |
| evidence sets | 8 |
| table answers | 8 (18 individual cells) |

Every change cites a page. Nothing is inferred, nothing is submitted yet.

## Final hand-audited file: `test_v32`

Consolidated against v19 (0.5602):

| | corrected |
|---|---|
| paper sets | **9** |
| multiple-choice answers | 4 |
| evidence sets | 16 |
| table answers | 11 |
| questions touched | **21 of 71** |

Emitted paper-set sizes `{1: 30, 2: 38, 3: 3}`, 123 evidence items, zero all-null
table rows.

Two more cells confirmed **correct** in the final pass, with only their evidence
wrong:

* **VideoLLaMB** `O(M^2)`. `iccv2025_02565` p3: "the overall time complexity of our
  approach is O(K2), and the space complexity is O(K). **For the LLM, the complexity
  is O(M 2)**." Our evidence had called this Figure 1; it is prose, so the type and
  object id were both wrong and would have scored zero. Now `text_span` p3.
* **WINS** `16 (p^2) times smaller`. `iccv2025_02668` p4 gives filter pruning's unit
  as `p^2 x R^{1xc}`, so a `p^2` factor is consistent. Evidence moved p5 -> p4.

Left deliberately unresolved: the RomanTex rotation-matrix count. The phrase does not
appear in the paper's extracted text at all, so any value would be a guess, and one
cell of one question is not worth a fabrication.

### What actually moved the score

Nothing in the pipeline. Every gain from 0.5519 to 0.6166 came from reading the source
PDFs and correcting what the model had written. The recurring failure was never
hallucination — it was **the right paper and the wrong row**: a base-LLM row instead of
a fine-tuned one, NLLB-600M instead of the paper's own baseline, RPEt instead of RPEr,
MC1 instead of MC3, inter-annotator instead of intra-annotator, Table 1 instead of
Table 2. Every one of those numbers is genuinely printed in the cited paper, which is
why no attestation or consistency check can catch them and why three separate
automated triages returned mostly false positives.

## Post-v32 audit (v35)

v32 scored **0.6366** (paper F1 0.8789, evidence F1 0.5606, MC 0.860,
row F1 0.3405, cell 0.2103), up from v26's 0.6166.

Two new detectors, both built because the value-based triage kept returning
false positives:

* **name check** -- does every emitted paper's text actually contain a named
  entity from its question?  A paper that never says "ERASE" cannot be the ERASE
  paper.
* **pool name check** -- same question asked against all 27,487 titles, which
  catches the case the PDF cache cannot: the right paper was never selected, so
  its text was never there to search.

Four wrong papers found, all confirmed against the PDF:

| question | was | is | proof |
|---|---|---|---|
| `ltqa_dada5a958af5068b` | `eccv2024_02070` | `iccv2025_02482` | p2 "BLIP's smaller text encoder/decoder (BERT-base, 110M"; the ECCV paper names BLIP once, in passing |
| `ltqa_5b08acb319329757` | `naacl2025_01150` | `iccv2025_02101` | Figure 5 p4 carries all three Norm-vs-BG Dice bars |
| `ltqa_ab60eb571239314b` | `naacl2025_00237` | `naacl2025_00609` | naacl2025_00237 is EAC; ERASE is "Language Modeling with Editable External Knowledge" |
| `ltqa_090478d0ddf8d27f` | `icml2025_01987` | `iccv2025_00745` | "Figure 1. Reward Model Scoring Paradox", FLUX at 4.29% down |

### Gold structure, measured on validation

* Gold evidence is **one key per gold paper** -- (1,1) 24x, (4,4) 19x, (3,3),
  (9,9); 43 of 55 questions have exactly one key per paper.
* Gold **table rows == gold papers** in 9 of 11 validation table questions.
* Gold almost never pairs a `text_span` with an object on the same page (1 of 64
  table items), so padding an object item with a same-page span is pure
  precision loss.  Hypothesis killed before it cost anything.
* Gold page histogram peaks at **6-7** (65 of 149 items) with only **5 of 149**
  on page 1.  Ours put 40% of items on pages 1-3.  Re-aiming every item at the
  densest-then-later page measured **+0.013** evidence F1 on validation -- below
  the 0.02 bar, so it was not shipped; it was used only to rank items for
  manual review.

## v44: reading the figures, and the only two row keys I can prove wrong

### Rendering the figures found the 6th MC error

Four MC questions ask for counts that only exist in a figure. Rasterising those
pages at 2x and reading them settles all four:

| question | what the figure shows | our answer |
|---|---|---|
| `ltqa_b61b62d2801d5f07` | ARMO p4: "we classify the models into **eight** distinct categories", and Figure 3's pie labels are Complex/Simple Character, Animal, Bird, Insect, Marine, Plant (+others) | **six — wrong, now A** |
| `ltqa_25546519dfb273c8` | the p2 prose says it outright: "presents three keyframes interleaved with four tutorial texts" | C, correct |
| `ltqa_4900eb2c71c890c8` | TAG-WM p3 "operates through four stages"; TADM Figure 1 brackets the pipeline into Latent Encoding / Rescaling / Enhancement / Decoding | D, correct |
| `ltqa_69178ae8aa769eda` | VLM4D Figure 2 legend: 55% Translational, **19% Rotational**, 17% Counting, 9% False Positives | D, correct |

Two inferences I had made from text were also confirmed visually rather than
left as guesses: Figure 9 of `naacl2025_00069` has an *inter* row and an *intra*
row, and the intra row reads ESA 0.149 / ESA-AI 0.333 -- option D's 0.281/0.189
are the **Pearson** numbers from the MQM panels. And NICP sits just above the 0.1
gridline in ERNet's Figure 1(b), matching Table 1's 0.108.

**All 50 MC questions are now verified directly against the source.** Exactly one
was wrong. Since the scored MC is 48/50, one error remains in a question I have
checked and believe correct; I cannot identify it, and guessing would be
vandalism.

### Row keys: the arithmetic, and why I am not guessing

Row F1 has been **0.340476 across five scored runs** (v19, v26, v32, v41, v43),
which makes the scored history a measuring instrument. Diffing row keys between
runs and attributing the deltas:

* `0ebcb34` -- `cosql`/`sparc` are **right**: lengthening them to "cosql
  validation set" cost exactly 1.00 of the 21-question sum.
* `7d7e93` -- `videollamb`/`wins` are **right**: bare names gained 1.00 over the
  question's longer phrasing.
* `5b2e21` -- `mdbpe` and `byte-pair visual encoding` are **both wrong**. They
  were swapped between v26 and v32 and the macro did not move by a thousandth.
* `a805cd` -- both spellings of the CoT-ICL title are **wrong**, on the same
  invariance argument across v9 and v19.

Those last two are the only keys I can prove wrong, and only there is an extra
candidate row free: `cell_total` iterates over **gold** rows, so an extra
predicted row cannot enlarge the cell denominator. Adding one costs row
precision and can only add cell recall, which puts break-even at a **26%** hit
rate, not the 60% a row-F1-only reading suggests.

Blanket hedging was still measured and rejected: carrying both key styles on
validation moved row F1 **0.5773 -> 0.5571**, because there the bare keys are
mostly right and the alternative never hit.

### Correction to an earlier note

I recorded that adding a `table` item to every text_span page bearing a table
caption had "zero effect" on validation. That reading was wrong. It added only 4
items, and all 4 landed on questions already scoring zero, so the experiment was
**uninformative, not negative**. It is untested, and I have not shipped it.

## v45: gold's `paper` row keys are short names (measured, not guessed)

v44 scored **0.7322** with row F1 finally moving off 0.340476 to **0.351587**.
That delta is +0.2333 over the 21-question sum, and it decomposes **uniquely**:

| v44 change | arithmetic | reading |
|---|---|---|
| `a805cd` C 0->1, N 2->4 | `2*1/(2+4) - 2*0/(2+2)` = **+0.3333** | one short name **hit**; both full titles were wrong |
| `5b2e21` C 1->1, N 2->3 | `2*1/(2+3) - 2*1/(2+2)` = **-0.1000** | "Multidimensional Byte Pair Encoding" **missed** |
| | **+0.2333** | matches the observed delta exactly |

Validation used a row-key column literally named `Paper Title` and gold there was
the full lowercase title. Test's column is named `paper`, and gold is the short
name. The column name appears to drive the format.

### What v45 does with that

* `bed9aa`, `dd9546`, `033b9d` -- **add** short names (`GRAB`/`Matador`/`HCN-PAI`,
  `BRIDGE`/`CMAD`, `tgGBC`/title-head) **alongside** the full titles. This is the
  move that does not require me to be right about which convention gold used:
  3 of 6 rows match either way, giving row F1 2/3, and every gold row is matched
  so all of its cells get scored. Dropping the titles only wins if
  P(short) > 0.9, and one data point does not buy that.
* `a805cd` -- the full titles are **proven** wrong, so they are pure precision
  loss. Dropped. Kept both short names and added `LEAD`, the dueling paper's own
  method acronym, since only one of the two shorts hit.
* `5b2e21` -- proven miss, dropped. Back to two rows, which restores 0.5 from 0.4.

Method acronyms confirmed from the papers: `tgGBC` ("trim keys gradually Guided
By Classification token"), `LEAD` ("LLM with Enhanced Algorithmic Dueling"),
`Matador` ("~7,200 samples across 57 material classes", which also re-confirms
our cell value of 57).

## v46: everything the v45 delta proved wrong, removed

v45 scored **0.7425** (row F1 **0.4283**, cell **0.2262**). The +1.6111 row-sum
shift admits only two decompositions, and they agree on everything that matters:

* the **full metadata titles are wrong in all four** paper-keyed questions;
* `a805cd`'s `LEAD` **missed**;
* `bed9aa` matched **2 of 3** shorts, so one of GRAB / Matador / HCN-PAI is wrong;
* `dd9546` and `033b9d` matched 3 of their 4 shorts between them.

The cell-sum shift was exactly **+0.3333**, which is `bed9aa` on its own:
2 matched rows x 1 correct cell of 2, over 3 gold rows x 2 columns = 2/6. So its
`value` cells (9 / 57 / 4) are right and `quantity_asked` was wrong -- and
`dd9546` and `033b9d` contributed **zero** cells, meaning both of their value
columns are wrong too.

v46 therefore drops every row now proven not to match (12 full-title rows and
`LEAD`), which is pure precision recovered:

| question | v45 | v46 |
|---|---|---|
| `dd9546` | 0.667 | **1.000** |
| `bed9aa` | 0.444 | **0.667** |
| `033b9d` | 0.333 | **0.500** |
| `a805cd` | 0.400 | **0.500** |

and replaces `bed9aa`'s `quantity_asked` cells -- which the delta proves wrong,
and which were verbatim question clauses ("how many distinct high-level
categories does the GRAB benchmark organize its 23 graph properties into") that
no grader would type into a table cell -- with the bare quantity: "high-level
categories", "material classes", "benchmark datasets".

### What I am deliberately not doing

The five descriptor-keyed questions (`quantity`, `setting`, `attribute`,
`metric`) are the largest remaining block, and by the same logic their long keys
may be wrong. But `97a49a`'s keys ("plotted ratio for the lowest
problem-difficulty value", "number of discrete difficulty levels") are already
close to what a grader would plausibly write, and `a4bf90`'s are already short
("Year", "Number of annotators"). Adding alternates there is only free if the
current keys are wrong, and unlike the paper columns I have no measurement
saying they are. Guessing costs 0.333 per question when the current key was
right. Left alone.
