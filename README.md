# LitTraceQA — GroundLM @ EMNLP 2026 Shared Task

System for the [LitTraceQA shared task](https://groundlm.github.io/grouplm_emnlp2026/shared-tasks.html#littraceqa):
answer a research question by finding the paper(s) in a 27,487-paper pool, locating
the specific evidence inside them (a table cell, a figure panel, an equation, a
citation), and emitting the answer in the requested shape.

**Deadline 19 Aug 2026 AoE.** See [plan.md](plan.md) for the full design, the
measured facts the design rests on, and the schedule.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash scripts/download_data.sh          # dataset is CC BY-NC 4.0, not vendored
cp .env.example .env                   # add GEMINI_API_KEY, OPENREVIEW_* credentials
```

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
    expand.py          cluster expansion + set-size policy
  pdf/
    fetch.py           per-venue routing, mirrors, disk cache
    mirrors.py         PMLR / papers.nips.cc title indices
exp/                   numbered, reproducible experiments
reports/               ablation results
scripts/               official evaluate.py / validate_submission.py (unmodified)
```

## Three things that decide this task

1. **The scoring code, read literally.** `answer.multiple_choice` takes `gold`,
   not `label`; freeform is exact match and absent from the test set; the
   evidence key is a coarse 4-tuple that ignores `row`/`column`/`region`.
   See plan.md §1.
2. **`multi_paper` gold sets are topical clusters, not answer sets.** 55
   validation questions collapse to 33 distinct gold sets; one 4-paper cluster
   is shared by 12 questions. Returning only the answer-bearing paper caps you
   at F1 = 0.40 on those. See plan.md §2.2.
3. **Titles are space-mangled and papers are named by acronyms that appear
   nowhere in their metadata.** `"AceMath"` is stored as `"A ce M ath"`; `"IMM"`
   is the initialism of *Inductive Moment Matching*. Both need dedicated
   indices. See plan.md §2.1, §2.3.

## Reproducing

```bash
.venv/bin/python exp/02_lexical_recall.py     # zero-cost retrieval ceiling
.venv/bin/python exp/03_hybrid_recall.py      # per-mention RRF fusion
.venv/bin/python exp/04_set_size_sweep.py     # how many papers to return
```

Evaluate a prediction file with the official scripts:

```bash
.venv/bin/python scripts/validate_submission.py --input data/test.jsonl --pred preds.jsonl
.venv/bin/python scripts/evaluate.py --gold data/validation.jsonl --pred preds.jsonl
```
