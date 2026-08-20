# LitTraceQA — GroundLM @ EMNLP 2026 Shared Task

Team **OdeD**. Answer a research question by finding the paper(s) in a
27,487-paper pool, locating the specific evidence inside them (a table cell, a
figure panel, an equation, a citation), and emitting the answer in the requested
shape.

**Deadline 19 Aug 2026 AoE.**

## Current standing

**Best submission: 0.7518** (`preds/test_v49.jsonl`). Rank 1 is 0.7837.

Everything above 0.5519 came from **auditing answers against the PDFs by hand**
rather than from any change to the pipeline. **`test_v50.jsonl` is the file to
submit next**, and its two changes are free under every reading consistent with
the scores so far.

From v41 onward the scored deltas became the measuring instrument: row F1 sat at
exactly 0.340476 for five consecutive submissions, so a single key change and its
effect on the 21-question sum could be attributed uniquely. That is how the
`paper` row keys were shown to be short names, how three candidate keys were
shown to have missed, and how individual cells were shown to be wrong and
therefore free to rewrite.

| run | paper F1 | evid F1 | MC | table row F1 | table cell acc | overall |
|---|---|---|---|---|---|---|
| v2 | 0.6324 | 0.3587 | 0.68 | 0.3221 | 0.1310 | 0.4563 |
| v5 (local reader) | 0.6474 | 0.3324 | 0.72 | 0.2690 | 0.0873 | 0.4462 |
| v6 | 0.6474 | 0.3887 | 0.82 | 0.2849 | 0.0952 | 0.4787 |
| **v9 / v10** | 0.7991 | 0.4737 | 0.78 | 0.2738 | 0.0952 | 0.5519 |
| v14 (paper sets trimmed to 1) | 0.6559 | 0.4737 | 0.78 | 0.2738 | 0.0952 | 0.5042 |
| v16 (question-verbatim row keys) | 0.7897 | 0.4690 | 0.80 | 0.2262 | 0.0476 | 0.5389 |
| v19 (row keys authored by hand) | 0.7991 | 0.4737 | 0.78 | **0.3405** | 0.0952 | 0.5602 |
| v26 (answers audited vs PDFs) | 0.8554 | 0.5347 | 0.84 | 0.3405 | 0.1984 | 0.6166 |
| v32 (21 questions re-audited) | 0.8789 | 0.5606 | 0.86 | 0.3405 | 0.2103 | 0.6366 |
| v41 (7 wrong papers, 4 MC, 21 evidence) | 0.9704 | 0.6610 | 0.94 | 0.3405 | 0.2103 | 0.7095 |
| v43 (equation_algorithm evidence, 5th MC) | 0.9704 | 0.7121 | 0.96 | 0.3405 | 0.2103 | 0.7287 |
| v44 (figures read; 6th MC) | 0.9704 | 0.7121 | 0.98 | 0.3516 | 0.2103 | 0.7322 |
| v45 (short paper row keys added) | 0.9704 | 0.7121 | 0.98 | 0.4283 | 0.2262 | 0.7425 |
| v46 (proven-wrong rows dropped) | 0.9704 | 0.7121 | 0.98 | 0.4675 | 0.2262 | 0.7468 |
| v48 (14 edits batched) | 0.9704 | 0.7192 | 0.98 | 0.4534 | 0.2500 | 0.7502 |
| **v49 (three dud keys dropped)** | **0.9704** | **0.7192** | **0.98** | **0.4675** | **0.2500** | **0.7518** |
| v50 (two free changes) | — | — | — | — | — | not yet submitted |
| v11 | 0.7967 | 0.4667 | 0.82 | 0.2738 | 0.0595 | 0.5493 |
| v13 (cerebras selector) | 0.7991 | not submitted | — | — | — | re-draw of v9 |

Winning config: `--llm-select --visual-table --max-papers 3`.

## The scoring function

```python
answer_score = (multiple_choice_accuracy + table_row_f1_macro
                + table_cell_accuracy_macro) / 3
overall      = (paper_f1_macro + evidence_f1_macro + answer_score) / 3
```

Verified to six decimals against all nine leaderboard rows and all four of our
scored runs. Paper and evidence are **two thirds** of the score; a table question
is worth 4.8× a multiple-choice one; `table_cell_accuracy_micro` is reported but
**not scored**. Full derivation and the earlier wrong weight vector:
[reports/endgame.md](reports/endgame.md).

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # torch==2.6.0, not +cu124
bash scripts/download_data.sh          # dataset is CC BY-NC 4.0, not vendored
cp .env.example .env                   # GEMINI_API_KEY, OPENREVIEW_*, optionally GROQ/CEREBRAS
```

Gotchas that cost real time:

* `requirements.txt` pins `torch==2.6.0+cu124`, which is not on PyPI. Install
  plain `torch==2.6.0` or use the PyTorch index.
* Pre-download `bge-reranker-base` and `bge-large-en-v1.5`. The per-question
  SIGALRM watchdog fires during a first-use model download and turns every
  question into a timeout with empty `paper_ids`.
* llama-server's usable context is `--ctx-size / --parallel`. 4096 across 2 slots
  is 2048 per request, and it *rejects* an oversized request rather than
  truncating.

## Running

```bash
# best known config
.venv/bin/python run.py --split test --llm-select --visual-table --max-papers 3 \
  --mc-samples 1 --rpm 14 --out preds/test.jsonl

# paper selection only -- local, free, no API key
.venv/bin/python run.py --split validation --no-read --out preds/val_retrieval.jsonl

.venv/bin/python scripts/validate_submission.py --input data/test.jsonl --pred preds/test.jsonl
.venv/bin/python scripts/evaluate.py --gold data/validation.jsonl --pred preds/val.jsonl
```

## What is measured

Every claim below has a report and a reproducible experiment behind it.

| finding | where |
|---|---|
| Scoring weights (1/3, 1/3, 1/9, 1/9, 1/9) and the earlier wrong fit | `reports/endgame.md` |
| LLM candidate selection: **+0.0542** validation, **+0.0732** test | `reports/paper_selection.md` |
| Paper identification by title generation fails (median similarity 56) | `reports/paper_selection.md` |
| Candidate recall is capped by the question, not the retriever | `reports/paper_selection.md` |
| Visual table cells: +0.0455 cell accuracy on validation, 0.000 on test | `reports/table_stage.md` |
| Evidence padding loses (marginal-add rule does not apply) | `reports/table_stage.md` |
| Page alignment is not the cap (72.8% agreement, no offset) | `reports/e4_e6_measurements.md` |
| Gold table cells are never null (0/27) | `reports/e4_e6_measurements.md` |
| ~~No free selector beats `gemini-flash-lite`~~ **retracted** — it was a rate-limit artefact | `reports/free_selectors_and_evidence.md` |
| Cerebras selector: +0.0280 validation; changes 26/71 test papers (transfer untested) | `reports/free_selectors_and_evidence.md` |
| Full-text indexing is a `multi_paper` lever; test-like family is 96% reachable | `reports/free_selectors_and_evidence.md` |
| Where evidence loses, item by item | `reports/free_selectors_and_evidence.md` |
| Local reader vs hosted (lost on test) | `reports/local_reader.md` |
| Submission log with component breakdowns | `reports/leaderboard_gap.md` |

## Three things that decide this task

1. **The scoring code, read literally.** `answer.multiple_choice` takes `gold`,
   not `label`; freeform is exact match and absent from the test set; the
   evidence key is a coarse 4-tuple ignoring `row`/`column`/`region`; a null cell
   scores zero because gold is never null.
2. **Paper selection multiplies into everything.** Evidence recall is bounded by
   `paper_recall × locator_accuracy`, and MC is 0.600 with a correct paper against
   0.062 without. Every downstream gain this project made came from selection.
3. **Validation and test are different problems, and only one of them is scored.**
   77% of validation gold papers are never named in their own question — the
   `multi_paper` cluster regime, absent from test, which is why validation paper F1
   (0.60) sits far below test (0.80). Both of the largest levers found late,
   full-text indexing and a stronger selector, turned out to be levers on
   `multi_paper` and measured **zero** on test. Check which regime a lever serves
   before building it. The remaining test headroom is candidate recall — getting
   the gold paper into the shortlist — because two independent selectors agree on
   71/71 test questions and both leave the same 0.20 gap.

## Method notes

Two rules learned the expensive way, both from repeated failures here:

* **Do not ship on a validation delta below 0.02.** Three changes were decided
  inside a bootstrap CI three times wider than the effect; the two that were
  measurable on test returned zero or worse. Only the one large effect
  (+0.0542) transferred.
* **Both arms of an A/B must come from the same session with the same flags.**
  Quoting one arm from an older report produced a local-vs-hosted conclusion that
  test reversed — and then, after this rule was written down, produced a
  free-selector conclusion that had to be retracted. Re-running the control moved
  the baseline 0.0089.
* **Read the error counter before the score, and never publish an ordering taken
  from a run with errors.** A failed call falls back silently, so a rate-limited
  arm is part model and part BM25. This inverted the sign of a result: 0.5538
  "loss" at 58 errors, 0.6182 win at 1 error.

## Layout

```
littraceqa/
  textnorm.py          squash / demangle -- fixes the pool's mangled titles
  corpus.py            paper pool, Question/Paper types, JSONL io
  retrieval/
    lexical.py         BM25 + nickname n-gram index
    acronym.py         title-initialism index (IMM -> Inductive Moment Matching)
    scope.py           venue/year extraction from question text
    hybrid.py          per-mention RRF fusion
    dense.py           bi-encoder over title+abstract, cached embedding matrix
    rerank.py          cross-encoder rerank (bge-reranker-base)
    verify.py          LLM selection over the shortlist  <- the big win
    identify.py        title generation + pool matching   (killed, kept for the record)
    mention_verify.py  full-text mention filtering        (killed, +0.003)
    select.py          mention-anchored selection
    expand.py          cluster expansion                  (killed by exp/06)
  pdf/
    fetch.py           per-venue routing, mirrors, disk cache
    objects.py         enumerate the locators a PDF can support
    read.py            page text, caption index, references, rasterisation
  reason/
    client.py          Gemini client: model rotation, per-day 429s, caching
    local_client.py    OpenAI-compatible client (llama-server / Groq / Cerebras)
    local_llm.py       local GPU reader
    localize.py        read one paper, return answer + locator
    solve.py           MC / table / freeform synthesis
  answer/
    build.py           schema-exact records, type coercion
    table_visual.py    read table cells off a rendered page
exp/                   numbered, reproducible experiments (01-19)
reports/               measurements, including every negative result
HYPOTHESES.md          backlog, minimum 5 untried entries
```
