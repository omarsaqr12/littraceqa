# Where we stand against the leaderboard

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
