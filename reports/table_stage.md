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
