# Endgame plan — 0.4787 → target 0.76+

**Written 16 Aug 2026. Deadline 19 Aug AoE. ~19 test submissions left.**

This supersedes the priority ordering in `leaderboard_gap.md` and `scoring_and_fixes.md`.
Both were built on a **misread of the leaderboard columns**, which produced the wrong
weight vector and pointed effort at the wrong stage. Section 1 fixes that; everything
after follows from it.

---

## 1. The scoring formula, exactly

The leaderboard columns are `evaluate.py`'s `metrics` dict in declaration order, with
`freeform_exact_match` showing `n/a`:

```
rank, team, overall, timestamp,
paper_precision_macro, paper_recall_macro, paper_f1_macro,
evidence_precision_macro, evidence_recall_macro, evidence_f1_macro,
multiple_choice_accuracy, freeform_exact_match,
table_row_f1_macro, table_cell_accuracy_macro, table_cell_accuracy_micro
```

The last three are **not** table P/R/F1. `0.5841 / 0.3254 / 0.3678` for ACF is
row-F1 / cell-acc-macro / cell-acc-micro. `docs/evaluation.md` on the HF repo confirms
the names and order.

Fitting all nine leaderboard rows recovers the aggregate exactly (max error 2e-5):

```
answer_score = (multiple_choice_accuracy + table_row_f1_macro + table_cell_accuracy_macro) / 3
overall      = (paper_f1_macro + evidence_f1_macro + answer_score) / 3
```

| team | predicted | reported |
|---|---|---|
| ACF | 0.78367 | 0.7837 |
| gabby | 0.78352 | 0.7835 |
| DKE | 0.77680 | 0.7768 |
| tus-nlp | 0.76502 | 0.7650 |
| usc | 0.75021 | 0.7502 |
| Everest | 0.57678 | 0.5768 |
| **OdeD** | **0.47871** | **0.4787** |
| OracleLadder | 0.32856 | 0.3286 |
| orgtest | 0.04817 | 0.0482 |

### 1.0 Independently re-verified against our own three scored runs

The formula reproduces every submission we have made, to **six decimal places** — a
stronger check than the leaderboard fit, because these rows were not used to derive it:

| run | answer_score | predicted | reported | error |
|---|---|---|---|---|
| v2, 13 Aug | 0.3777 | 0.45626 | 0.45626 | 0.000000 |
| v5 local, 16 Aug | 0.3588 | 0.44620 | 0.44620 | 0.000000 |
| v6 hosted, 16 Aug | 0.4001 | 0.47873 | 0.47873 | 0.000000 |

The superseded weight vector misses all three in the same direction:

| run | old formula | reported | error |
|---|---|---|---|
| v2 | 0.4815 | 0.4563 | +0.0253 |
| v5 | 0.4731 | 0.4462 | +0.0269 |
| v6 | 0.5057 | 0.4787 | +0.0269 |

A systematic +0.025-0.032 overshoot was visible from the first scored submission and was
noted as "the formula overshoots" without being chased down. That was the moment to refit;
instead two more configs were ranked under it.

### 1.1 What this changes

Weights in the overall score:

| metric | weight | scored over | value per question |
|---|---|---|---|
| `paper_f1_macro` | **1/3** | 71 | 0.00469 |
| `evidence_f1_macro` | **1/3** | 71 | 0.00469 |
| `multiple_choice_accuracy` | 1/9 | 50 | 0.00222 |
| `table_row_f1_macro` | 1/9 | 21 | 0.00529 |
| `table_cell_accuracy_macro` | 1/9 | 21 | 0.00529 |
| `table_cell_accuracy_micro` | **0** | — | 0 |

Three consequences the old weight vector hid:

1. **`table_cell_accuracy_macro` is a full 1/9 of the score and we are at 0.0952.**
   The previous fit folded table into a single 0.177 term. Table is really **2/9 = 22.2%**,
   split across two independently-graded metrics, and we are near the floor on both.
2. **A table question is worth 4.8x an MC question.** `(2/9)/21 = 0.0106` against
   `(1/9)/50 = 0.0022`. 21 questions carry more weight than 50.
3. **`table_cell_accuracy_micro` is reported but not scored.** Ignore it entirely.

### 1.2 Corrections to prior reports

- `scoring_and_fixes.md §1`: `overall = 0.364*paper + 0.337*evidence + 0.177*table + 0.108*MC`
  is **wrong**. It was fitted on five rows with the table column mislabelled. Real weights
  are 1/3, 1/3, 1/9, 1/9, 1/9.
- `leaderboard_gap.md §3`: "Their Table R (0.325) is far below Table P (0.536): they are
  **under-producing rows**." Those two numbers are row-F1 and cell-accuracy, not P and R.
  The leaders are not under-producing rows; they are **getting cells wrong**, which is a
  different problem and the one with the most headroom on the board.
- `local_reader.md`: the "weighted score" column re-ranks configs under the wrong weights.
  Re-score before trusting the local-vs-hosted conclusion. Under the true weights, table
  0.528 -> 0.437 costs 0.0101 while MC 0.390 -> 0.512 gains 0.0136 — the local reader still
  wins on validation by 0.0035, which is not a margin worth defending. On **test** it lost
  outright: 0.4462 against 0.4563 for the hosted reader.

---

## 2. Where the 0.305 actually is

| component | OdeD | ACF | gap | overall pts |
|---|---|---|---|---|
| paper F1 | 0.6474 | 0.9915 | 0.344 | **0.1147** |
| evidence F1 | 0.3887 | 0.7230 | 0.334 | **0.1114** |
| MC accuracy | 0.8200 | 1.0000 | 0.180 | 0.0200 |
| table row F1 | 0.2849 | 0.5841 | 0.299 | 0.0332 |
| table cell acc | 0.0952 | 0.3254 | 0.230 | 0.0256 |
| | | | | **0.3050** |

Cumulative scenarios:

| scenario | paper | evid | MC | row | cell | overall | rank |
|---|---|---|---|---|---|---|---|
| current | 0.647 | 0.389 | 0.82 | 0.285 | 0.095 | 0.4787 | 7 |
| + papers fixed | 0.990 | 0.389 | 0.82 | 0.285 | 0.095 | 0.5929 | 6 |
| + evidence at leader level | 0.990 | 0.720 | 0.82 | 0.285 | 0.095 | 0.7033 | 6 |
| + MC 1.00 | 0.990 | 0.720 | 1.00 | 0.285 | 0.095 | 0.7233 | 6 |
| + table at leader level | 0.990 | 0.720 | 1.00 | 0.584 | 0.325 | 0.7821 | 3 |
| **realistic 3-day target** | 0.950 | 0.600 | 0.94 | 0.750 | 0.550 | **0.7656** | 4 |
| **stretch** | 0.990 | 0.720 | 1.00 | 0.850 | 0.700 | **0.8533** | 1 |

Read the last two rows carefully. **Matching the leaders on paper, evidence and MC and
then matching them on table only gets you to 3rd.** The board is compressed at 0.75-0.78
precisely because five teams have all solved paper/MC and all failed at table. Nobody has
taken the 0.121 sitting above ACF in the table columns. That is the only differentiated
win available, and it is available to a team that never reaches paper F1 0.99.

---

## 3. What the leaderboard says about the leaders' architecture

Four teams report **paper precision = 1.0000 exactly**, with recall 0.975-0.989. ACF and
DKE report byte-identical paper *and* table numbers; gabby and tus-nlp share an identical
paper triple. That is not four independent IR pipelines converging.

Perfect precision on a 27,487-paper pool where 7.5% of titles are space-mangled and the
target papers are named by acronyms absent from their own metadata is **not reachable by
ranking title+abstract**. Our own oracle — keep exactly the gold papers already present in
top-40 — caps at 0.756 on validation.

The explanation that fits every number: **they are not retrieving, they are identifying.**
A frontier model with 2025-2026 literature knowledge (and/or search grounding) is asked
"which paper is this question about?", returns a title, and the title is matched into the
pool. `IMM -> Inductive Moment Matching` is a fact such a model knows; it is not a fact
recoverable from a bag of words over abstracts. Different teams running the same class of
model produce the same paper sets, which is exactly what identical rows look like.

**This is the drastic architectural change.** Retrieval stops being the primary mechanism
and becomes the fallback and the verifier.

Two corroborating details:
- Our MC accuracy is 0.82 with paper F1 0.647. The reader is answering correctly on many
  questions where we handed it the wrong paper — i.e. the model already knows this
  literature. We are using that knowledge downstream and refusing to use it upstream.
- `pin_exact_title_matches` was measured as a loss because `extract_nicknames` cannot tell
  which mention is the *subject*. An LLM can. The disabled feature was right; the mention
  extractor was wrong.

---

## 4. Architecture changes, in priority order

### C1 — Identify-then-match paper selection (replaces stages A-C) · +0.10 to +0.12

Current: mentions -> BM25/nickname/acronym/dense -> RRF -> cross-encoder -> top-n.
New: **identify -> match -> verify -> fall back.**

```
question
 ├─ 1. IDENTIFY  one call, gemini-2.5-flash + google_search grounding (free, 500 RPD)
 │     "Which paper(s) does this question refer to? Return exact titles,
 │      venue, year, and the expected number of papers."
 │     Structured output: {papers:[{title,venue,year,confidence}], n_expected}
 │
 ├─ 2. MATCH     titles -> pool ids via squash() + rapidfuzz over squashed titles,
 │     restricted by venue/year when given. squash() already defeats the
 │     "A ce M ath" mangling; this is the one place it is decisive.
 │
 ├─ 3. VERIFY    fetch each candidate PDF, extract full text, require the
 │     question's mention strings to occur. `\bIMM\b` appearing >=3 times in
 │     one paper and 0 times in the alternatives resolves it outright.
 │
 └─ 4. FALL BACK existing hybrid retriever, for questions where identify
       returns nothing that matches the pool.
```

Why verification matters independently: **precision is the half we are losing.** P=0.716
means ~28% of returned papers are wrong. Full-text presence/absence of a named artefact is
a near-zero-false-positive test and it is free after the download.

Scale of the download: top-10 candidates x 71 questions ~= 700 PDFs, deduplicated to maybe
500. At 10 concurrent fetches that is under an hour on the existing `pdf/fetch.py` routing.
This is the tractable version of the "venue-scoped full-text index" that `plan.md §4.3`
correctly identified as the only mechanism that can answer content-defined questions, and
wrongly deferred as an overnight job. You do not need the whole pool. You need the
shortlist.

### C2 — Rebuild the table stage · +0.05 to +0.09

This is currently the worst part of the system and the most valuable, and the cause is
structural, not prompt-level. `solve_table()` builds rows from `format_evidence()` — a
one-line-per-paper text digest of what the reader returned. The reader was asked a single
question and returned a single answer string. **You are asking a model to reconstruct a
table from a summary of an answer to a different question.** Cell accuracy 0.0952 is what
that produces. `local_reader.md` already found that rewriting `TABLE_PROMPT` changed nothing
— correct, because the prompt was never the constraint.

Replacement:

```
1. ROW KEYS FIRST, from the question and the paper set — never from the reader digest.
   Row keys are enumerable: dataset names, method names, model names, paper titles.
   The existing title-column special case is right; generalise it.
2. LOCATE the source table in the PDF (caption index from pdf/objects.py).
3. RENDER that page at 2x and hand the image + the required schema to the reader.
   Ask for every row and every column in one call. Tables are the one content type
   where text extraction reliably scrambles column alignment.
4. NORMALISE numbers to the paper's surface form. isclose(rel_tol=1e-6) means 85.3
   and 0.853 are different answers. Do not rescale percentages.
```

Three evaluator facts to exploit:

- **Never emit `null`.** `cell_equal` returns True only when gold *and* pred are both None.
  A wrong guess and a null score identically against non-null gold, so a guess is weakly
  dominant unless gold is genuinely null. The current prompt says "Use null for a cell you
  genuinely cannot determine" — that instruction is a strict loss on every non-null gold
  cell. Measure the gold null rate on validation first (§5, E6); if it is under ~10%,
  remove the instruction entirely.
- **Over-generate rows while row F1 is low.** Adding a candidate row with hit probability
  `p` raises expected row F1 iff `p > F1/2`. At 0.2849 that threshold is **0.14**. Emit any
  row you are 15% confident in.
- **A missed row key zeroes every cell in that row**, so row keys are strictly upstream of
  cells. Get keys right first, then fill.

### C3 — Evidence: audit the page alignment, then emit more · +0.05 to +0.10

Two separate problems.

**(a) Page alignment.** The evidence key grades `page` exactly. Gold carries a page on
149/149 validation items. If the organizers built gold from a different PDF rendering than
the one `pdf/fetch.py` returns (arXiv preprint vs camera-ready vs proceedings PDF), every
page is off by a constant and the entire evidence component is capped regardless of how
well the reader reads. **This has never been measured and it is a one-hour diagnostic.**
See E4. If there is a per-venue offset, correcting it is worth more than any prompt change.

**(b) We are emitting too few items.** Evidence P=0.4437 > R=0.3639 -> gold sets are ~22%
larger than ours. Validation gold averages 2.7 items/question (149 over 55). The marginal
rule for a set-F1 metric: add an item with hit probability `p` iff `p > F1/2` = **0.19** at
our current 0.3887. We are abstaining at the margin on a metric where abstention is never
rewarded — `collect_evidence`'s docstring already establishes this for the empty case but
the reader prompt still says "Do not pad the list; precision is graded as well as recall."
That is true and it is still worth padding, because F1 is below 0.4.

Same argument applies to papers: add a second paper whenever >= 0.32 confident
(`F1/2 = 0.6474/2`).

### C4 — Stop being free-tier-constrained · +0.02 to +0.04, ~$10

`plan.md §2.5` builds the whole architecture around a free-tier budget of ~250-1,000
requests/day, and `local_reader.md` describes fighting llama-server context limits to work
around it. Current state of the API (verified 16 Aug):

- `gemini-3.7-flash` — released 13 Aug 2026, "most capable Flash model for agentic
  workflows and multimodal reasoning", **free tier available**, 1M context, native PDF.
  This is a much stronger reader than `gemini-flash-lite-latest` or a local 27B Q4 GGUF.
- Google Search grounding is **not** on the free tier for 3.x, but **is** free on
  `gemini-2.5-flash` / `2.5-flash-lite` at **500 RPD**. That is the identify step in C1,
  free, with 7x headroom over the 71 questions.
- Paid tier 1 is one billing-account click. 3.7 Flash is $0.75/$3.75 per 1M. A full
  71-question run reading 3 papers at ~50k tokens each is ~10M input tokens ~= **$8**.

Free-tier limits are now per-project and only visible in AI Studio, so check the live
numbers before planning a run. But the framing to drop is that the budget is a hard
constraint. It costs less than a takeaway to remove it, and the shared task explicitly
permits APIs provided they are disclosed in the system paper.

---

## 5. Experiments

Ordered by (expected points) / (hours). Every one is measurable before submitting.

### E1 · Identify-then-match, validation + test — 3h — **run first**
Implement C1 steps 1-2 only (no verification yet). Measure paper F1 on validation, and on
the `hidden_source_single_paper` family specifically (26 questions, the test-like regime,
currently 0.846).
- **Success:** family paper F1 >= 0.95, overall validation paper F1 >= 0.60.
- **Kill criterion:** family F1 < 0.87 -> the model does not know these papers; fall back to
  C1 step 3 alone as a reranker over the existing candidate list.

### E2 · Full-text verification of the shortlist — 4h
Fetch top-10 candidates per test question. For each, extract text and score
`mention_hits(paper) = sum of occurrences of each extracted mention`. Drop candidates with
zero hits for every mention. Measure precision change on validation.
- **Success:** paper precision >= 0.95 with recall not dropping more than 0.02.
- Cache aggressively — these PDFs are the same ones stage D needs.

### E3 · Set-size calibration against the leaderboard — 1 submission
`predict_set_size` currently yields 1.408 papers/question and P/R = 1.16, so gold averages
~1.63. Raise the threshold for emitting a second paper to the marginal rule (p > 0.32),
submit, and read P and R off the board.
- P still >> R -> still too few, raise again. P < R -> too many, tighten.
- This is the only clean way to resolve the regime question `leaderboard_gap.md §5` posed,
  and it costs one submission.

### E4 · Page-offset audit — 1h — **highest value per hour in the whole list**
For every validation gold evidence item with an object id, find that caption in the fetched
PDF via `pdf/objects.py` and compute `gold_page - pymupdf_page`. Histogram it, split by
venue and by fetch source.
- All zeros -> alignment is fine, the reader is the constraint.
- Constant non-zero per venue -> apply the offset. This alone could move evidence F1 several
  points on every question from that venue.
- Wide spread -> we are fetching a different edition; switch source for that venue.

### E5 · Evidence set-size sweep — 2h
Sweep the number of emitted evidence items over {current, +1 same-page text_span, top-3
from the candidate list, top-4}. Measure evidence P, R, F1 on validation.
- Prediction from the marginal rule: the optimum is ~2.5-3 items while F1 < 0.5.
- Report bootstrap CIs; 55 questions means a 3-point difference is noise.

### E6 · Gold null-cell rate — 20 min
Count null cells in validation gold `answer.table.rows` over non-row-key columns.
- < 10% -> delete the "use null" instruction from `TABLE_PROMPT` and force a guess.
- > 25% -> keep nulls but only for columns where gold is frequently null.

### E7 · Table rebuild — 6h
C2 end to end. Measure `table_row_f1_macro` and `table_cell_accuracy_macro` separately on
the 11 validation table questions.
- **Success:** row F1 >= 0.65, cell acc >= 0.45.
- Validation has only 11 table questions, so confirm on test — table is 2/9 of the score
  and a regression here is expensive.

### E8 · Reader upgrade A/B — 2h
`gemini-3.7-flash` vs the local Qwen3.6-27B vs `gemini-flash-lite`, holding paper selection
fixed. Score under the **corrected** weights.
- Watch evidence F1 and cell accuracy, not MC. MC is 1/9 and already at 0.82.
- **Run both arms yourself.** The local-vs-hosted call was previously made by comparing a
  fresh local run against hosted numbers quoted from a report; it said local wins by
  +0.0033 and test said local loses by 0.0101.

### E9 · Use `test-extra` as the real dev set — 2h
`test_extra.jsonl` is 4,901 questions with its **own 5-submissions-per-day budget** on the
`littraceqa-test-extra` evaluator task, and the organizers explicitly recommend it for
diagnostics. Retrieval is local and free, so a paper-only prediction file over all 4,901
costs nothing but compute and returns paper P/R/F1 at **n ~= 4,901 instead of 55**.

This is the single most under-used resource in the competition. Every retrieval decision
currently being argued from 55 examples with 2-point noise bands can be settled properly.
Run E1, E2 and E3 variants through this track before spending a `test` submission on them.

Caveat: `test-extra` may not share the `test` distribution, so use it for **ranking configs**,
not for predicting the absolute test score.

### E10 · Local page retrieval for evidence (optional, only if time) — 4h
If E4 shows alignment is fine and the reader is still missing pages, add a ColQwen3-4B or
ColModernVBERT late-interaction pass over rendered pages of the selected papers, and hand
the reader the top-3 pages instead of the whole PDF. ColModernVBERT is 250M params and
lands within 0.6 NDCG@5 of ColPali, so it fits the 4080 alongside everything else. Only
worth it if page selection is demonstrably the bottleneck — do not build this on spec.

---

## 6. Schedule and submission budget

19 test submissions remain (4 today, 5 each on 17/18/19), plus ~20 on `test-extra`.
Submission days are counted in **America/Toronto**, and files failing sanity checks do not
count against the limit.

| when | do | submit |
|---|---|---|
| **16 Aug, rest of day** | E4 (page audit), E6 (null rate). Both are pure measurement, no pipeline changes. | E3 set-size probe — 1 test submission |
| **17 Aug am** | E1 identify-then-match. E9 harness: paper-only predictions over `test-extra`. | 2 x test-extra (identify vs current retrieval) |
| **17 Aug pm** | E2 verification. Apply E4's offset fix if one exists. | 1 x test — papers + evidence only, freeze answers |
| **18 Aug am** | E7 table rebuild. This is a full day's work; start early. | 1 x test-extra |
| **18 Aug pm** | E5 evidence sweep, E8 reader A/B. | 2 x test — table on, table off |
| **19 Aug am** | Freeze. Full rerun. Validate with `validate_submission.py`. | 2 x test, best config + one safe variant |
| **19 Aug** | Final submission **early**. AoE deadline, but do not use it. | — |

Rules for the endgame:
- **Never let the last submission of a day be an untested config.** Keep the best known
  file on the board at all times; the leaderboard shows the best successful submission per
  team, so a bad run cannot hurt you — but a bad run that is also your only run can.
- **Change one stage per submission** where the budget allows, so the board's P/R columns
  stay interpretable as a signal.
- Validate every file with the official validator before uploading. Malformed files do not
  consume budget, but they do consume the hour you spend confused.

---

## 7. Stop doing

- **Chasing `multi_paper` cluster recovery.** `exp/06` closed it and the test regime is not
  the cluster regime. Every hour spent here is worth zero on the board.
- **Tuning anything on 55 validation questions to three decimals.** Use `test-extra` (E9).
- **Freeform.** Zero test questions. Confirmed by `n/a` on every leaderboard row.
- **Citation-number handling.** 0 of 71 test questions mention a numbered reference.
- **`table_cell_accuracy_micro`.** Reported, not scored.
- **Optimising MC.** It is 1/9, we are at 0.82, and the remaining 0.18 is mostly gated by
  paper selection anyway (`scoring_and_fixes.md §5`: MC 0.600 with a correct paper, 0.062
  without). It will come along for free with C1.
- **Defending the local reader on principle.** It was chosen under a budget constraint that
  costs about $8 to remove, and its measured win over the hosted path shrinks to 0.0035
  under the corrected weights — and reversed on test.

---

## 8. The one-paragraph version

The overall score is `(paper_F1 + evidence_F1 + mean(MC, table_row_F1, table_cell_acc)) / 3`.
Paper and evidence are two thirds of it and we are at 0.65 and 0.39 against 0.99 and 0.72.
Paper selection is not a retrieval problem — four teams at precision exactly 1.0000 are
identifying papers with a model that knows the literature, then matching titles into the
pool, and we should do the same and verify with full text. Evidence is capped by an
unaudited page-alignment assumption and by emitting fewer items than gold on a metric where
abstention is never rewarded. And the table component — 2/9 of the score, where the leader
sits at 0.58/0.33 and we sit at 0.28/0.10 — is currently reconstructing tables from a text
digest of a single answer string, which is the one part of the system that has to be
rebuilt rather than tuned. Fixing paper, evidence and MC to leader level reaches 3rd place;
the table is the only place a first-place score exists.
