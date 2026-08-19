# Hypothesis backlog

Minimum 5 untried entries at all times. Below 5 triggers the research protocol in
`reports/endgame.md`. Each entry: what, which component, expected delta in **overall**
points, cost, and how it dies.

Current standing: **0.4787**, rank 7/9. Rank 1 is 0.7837.
Component weights: paper 1/3, evidence 1/3, MC 1/9, table row F1 1/9, table cell acc 1/9.

---

## Closed this session

| id | hypothesis | outcome |
|---|---|---|
| H1 | identify-then-match by generated title | **killed** — 0/29 titles within 80% of gold, median 56 |
| H1b | LLM recognition over candidates | **SHIPPED, +0.0542 val / +0.0732 test** |
| H2 | rebuild the table data path | partial — cell acc +0.0455 val, **0.000 test** |
| H3 | record fetch source, re-audit pages | fixed the reporting bug; 47/67 papers predate tracking |
| H4 | emit evidence to the marginal threshold | **killed** — recall +0.032, precision −0.028 |
| H7 | full-text mention verification | **killed** — 1 paper dropped in 55, +0.003 |
| H8 | over-generate table rows | folded into H2; row keys are not the constraint |
| H14 | cerebras `gpt-oss-120b` as selector, single-stage swap | **+0.0280 val, CI [−0.012, +0.081]** — retracts the earlier "no free selector wins"; submitted as v13 |
| H15 | full-text index to lift 71% -> 89% reachability | **killed** — the whole 18-pt gap is in `multi_paper`; test-like family is already 96% reachable |
| — | deeper LLM shortlist (20→30) | +0.0109 val, **−0.0026 test** |
| — | selector self-consistency (3 votes) | +0.0085, CI [−0.023, +0.052] — not shippable |
| — | free selectors (gpt-oss-120b, glm-4.7, qwen) | all **below** flash-lite |

## Still open

## H16 · A shared rate limiter across clients

The reader and the selector hold independent `RateLimiter` instances against one
provider quota, so their sum exceeds the cap and the excess becomes silent
fallback to the top BM25 candidate. This one defect inverted the free-selector
table (0.5538 "loss" vs 0.6182 measured clean). Every multi-client run in this
repo is suspect until it is fixed. **Test:** move the limiter to a module-level
registry keyed by base_url; re-run the three-stage Cerebras config, which was
abandoned for exactly this reason.

## H17 · Cerebras selector with self-consistency voting

`LLMPaperSelector.select()` already supports majority vote over samples, and at
~\$0.001/call three votes over 71 questions is \$0.21. Voting paid nothing on
`flash-lite`, but a 120B model with a wider output distribution is the case where
it should. **Test:** `--llm-select-samples 3` against the v13 config; the
comparison is free of the baseline-drift problem because v13 is in-session.

## H5 · `test-extra` as the statistical dev set
**Component:** all · **Expected:** indirect · **Cost:** 2h

4,901 questions with a separate 5/day budget on `littraceqa-test-extra`. The
single most under-used resource: every decision this session was argued from 55
questions with 2-point noise bands, and three of them were wrong. Retrieval is
local and free, so a paper-only file over all 4,901 costs compute only — but
`--llm-select` needs API calls, so a full-pipeline run over 4,901 is not free.
Sample 500 for a ±0.03 band at ~500 selector calls.

**Dies if:** it ranks configs differently from `test` twice running.

## H9 · Re-test `gemini-3.7-flash` as selector with thinking genuinely on
**Component:** paper F1 (1/3) · **Expected:** unknown · **Cost:** 1h + quota

Still **untested**, not disproven. Its one measurement (0.4982, returning exactly
one paper on all 55 questions) was taken with thinking disabled by the client's
global setting, and the retest died after one call on a per-day 429. The
cache-key bug that would have silently invalidated the retest is fixed.

**Dies if:** with thinking on it still returns a near-constant number of papers —
that would mean the uniformity is the model, not the configuration.

## H10 · Row keys from a dedicated extraction call
**Component:** table row F1 (1/9) · **Expected:** +0.02 to +0.05 · **Cost:** 2h

Row F1 is 0.2738 on test and has not moved across four submissions and three code
paths. Rows come either from the question's enumeration or from the retrieved set;
q_030 scores 1.00 with zero readings, q_025 scores 0.00 because its four rows are
four papers. A call that names the row keys before any reading separates them.

**Dies if:** extracted row keys match gold no better than the current implicit path.

## H11 · Backfill fetch sources and re-run the page audit
**Component:** evidence F1 (1/3) · **Expected:** +0.00 to +0.03 · **Cost:** 2h

47 of 67 gold-evidence papers predate source tracking. Re-fetch with `force=True`,
then split the 27% page disagreements by source. E4 found no per-venue offset, but
never got to test per-*source*.

**Dies if:** deltas stay uncorrelated with source — the annotators used an edition
we cannot obtain and 73% is the ceiling on anchored pages.

## H12 · Emit a second locator only on high-agreement papers
**Component:** evidence F1 (1/3) · **Expected:** +0.01 to +0.03 · **Cost:** 2h

Blanket padding failed (H4) because the reader's second locator is drawn from the
same distribution as its first, and the first is right ~50% of the time even on a
correctly selected paper. But the decomposition shows 18 of 25 addressable errors
are *wrong page, right paper and type* — so a second locator restricted to the
same paper and a different page targets a specific failure rather than padding
blindly.

**Dies if:** precision falls faster than recall rises, as in H4.

## H13 · Cross-check the reader's page against the caption index
**Component:** evidence F1 (1/3) · **Expected:** +0.01 to +0.03 · **Cost:** 1h

`use_pdf_locators` already has the reader pick an index into a mechanically-built
candidate list, so pages should be exact by construction — yet 18 of 25 locator
errors are page errors. Either the reader picks the wrong candidate, or the
candidate list itself carries the wrong page. Instrumenting which would say
whether this is a reader problem or a `pdf/objects.py` problem.

**Dies if:** the reader's picks already agree with the caption index — then the
errors are edition differences and E4's 73% ceiling binds.
