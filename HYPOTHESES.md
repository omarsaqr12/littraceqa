# Hypothesis backlog

Minimum 5 untried entries at all times. Below 5 triggers the research protocol in
`reports/endgame.md`. Each entry: what, which component, expected delta in **overall**
points, cost, and how it dies.

Current standing: **0.4787**, rank 7/9. Rank 1 is 0.7837.
Component weights: paper 1/3, evidence 1/3, MC 1/9, table row F1 1/9, table cell acc 1/9.

---

## H1 · Identify-then-match paper selection *(in progress — E1)*
**Component:** paper F1 (1/3) · **Expected:** +0.08 to +0.11 · **Cost:** 3h

Four teams report paper precision *exactly* 1.0000 on a 27,487-paper pool. Our oracle
over top-40 caps at 0.756, so ranking title+abstract cannot get there. They are asking a
model that knows the 2025 literature which paper the question means, then matching the
returned title into the pool. Our own MC is 0.82 at paper F1 0.647 — the reader already
answers from parametric knowledge on questions where we hand it the wrong paper.

**Dies if:** `hidden_source_single_paper` family F1 < 0.87 (currently 0.846).
**Successor:** same model as a reranker over the existing top-40 titles, which tests the
knowledge hypothesis without requiring exact title reproduction.

## H2 · Rebuild the table data path *(queued — E7)*
**Component:** table row F1 + cell acc (2/9) · **Expected:** +0.05 to +0.09 · **Cost:** 6h

`solve_table()` reconstructs a table from `format_evidence()`, a one-line-per-paper
digest of a single answer string. Cell accuracy 0.0952 is what that produces. Rewriting
`TABLE_PROMPT` gave byte-identical output, which confirms the prompt was never the
constraint — the data path is. Replace with: row keys from the question, locate the
source table via the caption index, render that page at 2x, ask for all rows and columns
in one call against the schema.

**Dies if:** cell acc < 0.20 on the 11 validation table questions.
**Successor:** dedicated PDF table parser (MinerU / Marker 2) feeding the schema
directly, rather than a VLM read.

## H3 · Record fetch source per paper, then re-audit page deltas
**Component:** evidence F1 (1/3) · **Expected:** +0.00 to +0.04 · **Cost:** 1h

E4 found 27% of anchored gold locators land on a different page than ours, with no
per-venue constant — so some papers are a different *edition* (arXiv vs camera-ready vs
proceedings). `fetch_status.json` records "cached" for anything already downloaded, so
the audit could not split deltas by source. Record the true source at download time,
re-run exp/10 split by it, and if one source is systematically wrong for a venue, switch
that venue's routing.

**Dies if:** deltas are uncorrelated with fetch source — then the annotators used
something we cannot obtain and 73% is the ceiling on anchored pages.

## H4 · Emit evidence up to the marginal-add threshold
**Component:** evidence F1 (1/3) · **Expected:** +0.03 to +0.06 · **Cost:** 2h

Evidence P (0.444) > R (0.364) in all three scored runs, so gold sets are ~22% larger
than ours. On a set-F1 metric, adding a candidate with hit probability `p` raises
expected F1 iff `p > F1/2` = **0.19** at our 0.389. We are abstaining well above that
threshold while the reader prompt still says "Do not pad the list". Validation gold
averages 2.7 evidence items per question; we emit ~1.4.

**Dies if:** a sweep over {+1 same-page text_span, top-3, top-4} lowers F1 on validation
with bootstrap CIs excluding zero.

## H5 · `test-extra` as the statistical dev set
**Component:** all · **Expected:** indirect, unlocks everything else · **Cost:** 2h

4,901 questions with a separate 5/day submission budget on `littraceqa-test-extra`.
Retrieval is local and free, so a paper-only file over all 4,901 costs compute and
returns paper P/R/F1 at n≈4,901 instead of 55. Every retrieval decision currently argued
from 55 examples with 2-point noise bands can be settled properly.

**Dies if:** the split's paper F1 ranks configs differently from `test` on two
consecutive comparisons — then it is a different distribution and only useful for
absolute coverage checks.

## H6 · Ask the reader for the answer *and* the option letter in one call
**Component:** MC (1/9) · **Expected:** +0.01 to +0.02 · **Cost:** 1h

Already partly done — `localize.OPTIONS_BLOCK` shows the reader the options and
`solve_multiple_choice` votes on `Reading.label` before falling back to a prompt over
the text digest. But the digest path still runs when no reading carried a label, and it
re-decides from a summary that has thrown the PDF away. MC is 0.82 against the leaders'
1.000, and the residual is mostly gated by paper selection (0.600 with a correct paper,
0.062 without), so this only pays after H1.

**Dies if:** MC given a correct paper does not move above 0.85 on validation.

## H7 · Verify paper choice by full-text mention counting
**Component:** paper F1 (1/3) · **Expected:** +0.03 to +0.06 · **Cost:** 4h

Paper precision is 0.716, so ~28% of returned papers are wrong. A named artefact
appearing three or more times in one candidate and zero times in the alternatives
resolves the choice outright, and it is nearly false-positive-free. The PDFs are the
same ones stage D needs, so the download is not wasted.

**Dies if:** precision gain < 0.05, or recall drops more than 0.02 because mentions are
absent from papers that are nonetheless gold.

## H8 · Over-generate table rows while row F1 is low
**Component:** table row F1 (1/9) · **Expected:** +0.02 to +0.04 · **Cost:** 1h

Marginal-add threshold for rows is `F1/2` = **0.14** at our 0.285. Any row we are 15%
confident in is worth emitting. We currently emit 56 rows across 21 test table questions
(2.7/question) and several questions collapse to a single row.

**Dies if:** row F1 falls on validation when row count is raised — meaning the extra
rows are worse than random, not merely uncertain.
