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
