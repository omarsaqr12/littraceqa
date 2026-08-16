# Where we stand against the leaderboard

> **CORRECTION (16 Aug 2026):** the columns labelled "Table P / Table R / Table F1"
> throughout this document are actually `table_row_f1_macro`,
> `table_cell_accuracy_macro`, `table_cell_accuracy_micro`. §3's conclusion that
> the leaders "under-produce rows" is therefore wrong: their row F1 is 0.5841 and
> their *cell accuracy* is 0.3254. They place rows better than we do and get the
> cells wrong -- which is where the remaining headroom on the board is.
> See `endgame.md §1`.

Leaderboard snapshot (test split, as of 10 Aug 2026):

| Rank | Team | Overall | Paper F1 | Evid. F1 | MC Acc | Table F1 |
|---|---|---|---|---|---|---|
| 1 | ACF | 0.7698 | 0.987 | 0.702 | 1.000 | 0.368 |
| 2 | DKE | 0.7689 | 0.987 | 0.702 | 1.000 | 0.368 |
| 3 | Everest | 0.5768 | 0.762 | 0.441 | 0.920 | 0.287 |
| 4 | gabby | 0.4575 | 0.587 | 0.491 | 0.700 | 0.012 |
| 5 | orgtest | 0.0482 | 0.000 | 0.085 | 0.180 | 0.000 |

Ours, measured on **validation** (different split — see the regime note below):

| | value |
|---|---|
| Paper F1 | 0.410 |
| Evidence F1 | 0.265 (**0.487–0.619** given a correct paper) |
| MC accuracy | 0.390 (**0.619** given a correct paper) |
| Table row F1 | **0.528** |

`Freeform` is `n/a` for every team, confirming the test split carries no
freeform questions (50 MC + 21 table). Optimising exact-match freeform would
have been wasted effort.

## 1. The test split is the named-paper regime, and that is now settled

The top two teams score **paper F1 0.987**. On validation that is not merely
hard, it is unreachable: an *oracle* that keeps exactly the gold papers already
present in our top-40 candidate list caps at **0.756** (exp/04), and exp/06
showed the `multi_paper` gold clusters are not recoverable from title+abstract
at any k — seeded with a *gold* paper, kNN returns 20% of its siblings at k=3.

No system scores 0.987 against clusters defined by full-text properties. So the
test split's gold must be **the papers the question names**, which is also what
the test phrasing suggests ("the **two** ICCV 2025 papers", 24 of 71 questions
state a count).

Consequence: **validation paper F1 systematically understates test performance**,
and tuning stage C on validation optimises for the wrong regime. This is why
`--selection mention_anchored` exists and is what the test submission uses.

## 2. Everything is gated by paper selection

Conditioning validation results on whether we retrieved any gold paper:

| | n | MC acc | Evidence F1 |
|---|---|---|---|
| papers overlap gold | 30 | 0.619 | 0.487 |
| papers miss entirely | 25 | 0.150 | 0.000 |

MC lands *below random* (0.25) when the paper is wrong — the reader is answering
from the wrong paper and confidently picking a distractor. There is no partial
credit path: fix selection or nothing downstream matters.

Our evidence-given-correct-paper (0.619) is already close to the leaders' 0.702,
so the localisation stage is not the problem.

## 3. Table is the field's weak spot and our relative strength

Rank 1 scores **0.368** on table — the lowest component for every team on the
board. Their Table R (0.325) is far below Table P (0.536): they are
**under-producing rows**. Our row keys are enumerated from the question text
("... on the Fake2-contaminated versions of SciFact, HotpotQA, NFCorpus, and
Climate-FEVER" *is* the row-key list), which attacks recall directly, and after
the response-schema fix we score 0.528 row F1 on validation.

Ranks 1 and 2 are identical on paper, evidence, and MC, differing **only** in
table precision (0.536 vs 0.529) — table precision is literally the tiebreaker
at the top of the board. Table is where a differentiated result is available;
21 of 71 test questions are table-only.

## 4. Priority order

1. **Paper selection for the named-paper regime** — gates everything, and the
   ceiling is 0.987 rather than validation's 0.756.
2. **Table recall** — the field's weakest component and our strongest.
3. **Evidence** — already competitive once papers are right.
4. **MC** — solved by the leaders at 1.000, so it follows from 1 and 3.

Nothing here justifies further tuning against validation's cluster regime.

## 5. Submission log

| file | selection | papers/q | empty evidence | MC label spread |
|---|---|---|---|---|
| `test_v1_mention_anchored.jsonl` | mention-anchored, no rerank | 2.79 (7 questions with none) | 45/71 | A=25 B=9 C=8 D=8 |
| `test_v2_rerank.jsonl` | fused + cross-encoder rerank | 1.14 | 29/71 | A=16 B=7 C=11 D=16 |
| `test_v3.jsonl` | fused + rerank, PDF-derived locators | **1.408** | **0/71** | A=15 B=5 C=12 D=18 |
| `test_v4.jsonl` | v3 + measured evidence-type prior | 1.408 | 0/71 | A=16 B=6 C=11 D=17 |

**v4 is the current-code submission.** It differs from v3 only in the reader
prompt and is close to indistinguishable from it: the `text_span` share of
emitted evidence is 55% in both, so the prior did not move the test distribution
even though it moved validation slightly. Submit either; v4 is the one the
repository reproduces today.

v3 (16 Aug, 121 calls, all `gemini-flash-lite-latest`) moves every proxy in the
right direction. The changes behind it are measured in
[scoring_and_fixes.md](scoring_and_fixes.md); the three that matter most:

* **No question abstains any more.** 29 questions previously emitted no evidence
  and scored a guaranteed zero on 33.7% of the total. Now 0 do.
* **Locators come from the PDF, not the model.** Page and object id are both
  graded exactly and both are printed in the paper, so the reader picks an index
  into a list built by PyMuPDF instead of generating a page number.
* **Set sizing was broken by a regex that could not match a hyphen**, which read
  "the two ICCV 2025 alignment-related adversarial papers" as a single-paper
  question. Papers per question 1.14 -> 1.408.

On the `hidden_source_single_paper` family -- the closest validation analogue to
the test regime -- the same pipeline scores paper F1 0.846 and evidence F1 0.538.

v2 improves every available proxy. The MC spread is the most telling: `A` is the
fallback label emitted when the solver fails, so 25 -> 16 means genuinely fewer
failures, not a different guessing pattern.

### The open question v2 is designed to answer

v2 returns **1.14 papers per question**. Set sizing cannot be settled on
validation, because validation is the cluster regime (gold sets of 1 or 4) where
the current policy is already optimal:

| sizing policy (on reranked candidates) | validation paper F1 |
|---|---|
| `predict_set_size` (v2) | **0.490** |
| always 1 | 0.480 |
| always 2 | 0.397 |
| max(1, distinct mentions, capped 4) | 0.466 |

If the test split is the named-paper regime and its questions name two papers,
returning one caps F1 at 0.67 on those. **The leaderboard reports Paper P and
Paper R separately, which resolves this in a single submission:**

* `Paper P` >> `Paper R` -> we are returning too few; raise the set size.
* `Paper P` << `Paper R` -> too many; tighten it.

Top teams report P=1.000, R=0.982, so the target shape is "return exactly the
named papers, no padding".


## 6. Scored submissions (OdeD)

All three verified against the corrected formula in `endgame.md §1`
(`(paper_f1 + evidence_f1 + mean(MC, row_f1, cell_acc_macro)) / 3`), which
reproduces each to six decimals.

| submitted | file | paper P / R / F1 | evid P / R / F1 | MC | row F1 | cell acc | **overall** |
|---|---|---|---|---|---|---|---|
| 13 Aug 22:10 | `test_v2_rerank` | .775 / .567 / **.632** | .425 / .329 / **.359** | .680 | .322 | .131 | **0.4563** |
| 16 Aug 09:44 | `test_v5_local` | .716 / .616 / **.647** | .399 / .305 / **.332** | .720 | .269 | .087 | 0.4462 |
| 16 Aug (v6) | `test_v6_hosted` | .716 / .616 / **.647** | .444 / .364 / **.389** | .820 | .285 | .095 | **0.4787** |

What the three runs establish, holding one stage at a time:

* **The set-size fix is a real win.** v2 -> v5 changed paper selection only:
  recall +0.049 for precision -0.059, net paper F1 +0.015. Kept in v6.
* **The hosted reader beats the local one.** v5 -> v6 changed only the reader,
  on identical paper selection: evidence F1 +0.056, MC +0.100, row F1 +0.016,
  cell acc +0.008. Every component improved. This is the clean A/B that
  `local_reader.md` should have run and did not.
* **Table is untouched by any of it.** Row F1 has moved .322 -> .269 -> .285 and
  cell accuracy .131 -> .087 -> .095 while everything else improved. Nothing
  tried so far addresses it, which is the argument for `endgame.md` C2.

Evidence P > R in all three runs (.444 vs .364 in v6), so we are still emitting
fewer items than gold on a metric that never rewards abstention.
