# LitTraceQA — OdeD's system for GroundLM @ EMNLP 2026

Team **OdeD** (Omar Saqr, Mostafa Gafaar — The American University in Cairo).

**Task.** Answer a research question by finding the paper(s) in a 27,487-paper
pool, locating the specific evidence inside them (a table cell, a figure panel,
an equation, a citation context), and emitting the answer in the requested shape
— multiple choice or a structured table.

**System paper:** [`paper/littraceqa_system.pdf`](paper/) — *OdeD at GroundLM 2026
Shared Tasks: Reading the Scorer for Literature-Grounded QA*.

## Result

| | official score |
|---|---|
| first submission | 0.4563 |
| best **fully automated** run | **0.5519** |
| best submission | **0.7649** (`preds/test_v57.jsonl`) |

The gap between 0.5519 and 0.7649 is per-question auditing against the source
PDFs plus leaderboard-feedback attribution, not a system that would generalise.
The paper says so in the abstract and the limitations, and reports the two
submissions that regressed alongside the ones that helped.

## What is worth reading here

Most of the score came from studying the scorer rather than from modelling, so
the findings live in `reports/`:

| file | what it records |
|---|---|
| `reports/scoring_and_fixes.md` | the metric decomposition, and score-guided attribution — decoding the macro metrics arithmetically to identify *which* prediction is wrong |
| `reports/table_stage.md` | the annotation conventions recovered from 55 dev examples: one evidence key per paper, gold table rows = paper count (8/8), row keys reproduce the paper's printed labels |
| `reports/free_selectors_and_evidence.md` | the evidence type conditionals (figure 10/10, table 3/3, equation 4/7) and the seven wrong papers found by entity-presence checks |
| `reports/paper_selection.md` | retrieval, reranking, shortlist recall saturation |
| `HYPOTHESES.md` | what was tried and refuted, with the measurement that killed it |

Six heuristics were measured and dropped, and four bugs in our own verification
scripts are documented — an analysis pipeline is itself an instrument, and ours
was wrong four times in ways invisible until checked.

## Reproducing

    bash scripts/download_data.sh          # data is not committed (CC BY-NC 4.0)
    cp .env.example .env                   # add your own API keys
    python run.py --llm-select --visual-table --max-papers 3 --split test

`preds/` and `logs/` are gitignored, so `reports/` is the record of every
measurement. The five verifiers that ran over every candidate submission, and the
scripts that generated the paper's figures, are included.

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
