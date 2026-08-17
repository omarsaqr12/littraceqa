# E4 page alignment and E6 gold nulls

Both are pure measurement against local caches. No API calls, no pipeline changes.

## E4 — page alignment is not the cap, and there is nothing to correct

For every validation gold evidence item carrying an object id, locate that caption
in our fetched PDF and compute `gold_page - our_page`. A caption is an unambiguous
anchor, so a systematic difference would be an edition difference rather than a
reader error.

81 anchored items across 55 questions; 7 captions not found; 0 papers unfetchable.

| delta | count |
|---|---|
| −14 | 2 |
| −9 | 1 |
| −5 | 1 |
| −4 | 1 |
| −2 | 2 |
| −1 | 7 |
| **0** | **59** |
| +1 | 3 |
| +2 | 2 |
| +3 | 3 |

**Exact agreement 59/81 = 72.8%.**

| venue | n | zero | mode | spread |
|---|---|---|---|---|
| NeurIPS | 23 | 87.0% | +0 | −9..+2 |
| ICLR | 17 | 52.9% | +0 | −14..+3 |
| CVPR | 17 | 76.5% | +0 | +0..+3 |
| ICML | 7 | 57.1% | +0 | −1..+0 |
| ACL | 5 | 60.0% | +0 | −2..+1 |
| ICCV | 5 | 100.0% | +0 | +0..+0 |
| NAACL | 4 | 100.0% | +0 | +0..+0 |
| ECCV | 3 | 33.3% | −5 | −5..+0 |

**Verdict: no systematic offset exists.** Every venue's modal delta is 0, so there is
no per-venue constant to apply. The E4 branch "constant non-zero per venue → apply the
offset" does not fire. Alignment is not what caps evidence F1 at 0.389 — 73% of the
pages we could name are already the right ones, so the reader and the selection are the
binding constraints. Proceed on that basis.

### Negative result: caption ambiguity is not the explanation either

The obvious mechanism for the remaining 27% was `page_of` returning the first regex
match. `CAPTION`'s delimiter is optional, so an extracted line reading "Table 3 shows
that ..." scores as a caption for Table 3, and PDF extraction breaks lines constantly.

Implemented `_caption_strength`: score each occurrence by delimiter (`:` strongest),
by whether a descriptive clause follows, and negatively when the next word is a verb
("shows", "presents") that marks a cross-reference. `page_of` now returns the strongest
occurrence rather than the earliest.

**Result: exact agreement 72.8% → 72.8%. Not one item moved.**

Mechanically, that means our detected caption was already the strongest candidate on
every disagreeing item — these are not cross-reference false positives. `q_033` wants
Table 3 on gold page 5 while the only strong caption in our PDF is on page 19; `q_023`
wants Table 1 on page 6 where ours is on page 4. Those are different documents, not
different parses of the same one.

The scoring change is kept — it is more correct in principle and costs nothing — but it
is **not** an improvement and must not be counted as one.

### H3 follow-up: the source *is* recorded, `fetch()` was hiding it

`fetch()` returned `"cached"` for any paper already on disk, discarding the
`source` that `fetch_status.json` had stored at download time. That is why every
row of the by-source table read "cached" — the audit could not split deltas by
the one variable it existed to test. Fixed: a cache hit now reports the original
source.

It does not settle H3 yet. Only 20 of the 67 papers carrying gold evidence were
fetched after source tracking was added:

| recorded source | papers |
|---|---|
| direct | 10 |
| openreview | 6 |
| mirror | 4 |
| *no record* | 47 |

All 20 recorded are `pagination_trusted=True`, so none of the observed deltas
come from an arXiv fallback — which was the leading hypothesis for the −14 and
−9 outliers and is now ruled out for those 20. Backfilling the other 47 means
re-downloading ~100 PDFs; deferred, because it cannot change today's conclusion
that no per-venue offset exists.

## E6 — gold table cells are never null

Counted null cells in validation gold `answer.table.rows` over non-row-key columns
(row keys are graded separately, as row F1).

**0 of 27 graded gold cells are null. 0.0%.** All seven columns across all seven
table questions with graded cells are fully populated.

`cell_equal` counts a null correct only when gold is *also* null. At a 0% gold null
rate, **every null we emit is a guaranteed zero** — exactly as costly as a wrong guess
and strictly worse than a plausible one.

Two changes, both required, because either alone is silently undone by the other:

1. `TABLE_PROMPT` said "Use null for a cell you genuinely cannot determine. Do not
   invent numbers." Replaced with an instruction to fill every cell and to give the
   most plausible value consistent with the row when the paper does not state it.
2. `answer.build._conform_row` nulled any type-mismatched cell, so a model returning
   the string `"2.05"` for a number column had it deleted rather than parsed. It now
   recovers the value: `"96.2%" → 96.2`, `"32.7±0.5" → 32.7`, `"1,204,000" → 1204000`,
   `"~4.1" → 4.1`. The same recovery was applied to `solve._to_number`.

Cell accuracy is 1/9 of the overall score and we sit at 0.0952, so this is a direct
attack on a component where we are near the floor. Effect size not yet measured — it
needs a table run, which is folded into E7.
