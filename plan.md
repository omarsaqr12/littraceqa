# LitTraceQA — Competition Plan (v2)

**Deadline: 19 Aug 2026 AoE. Today: 11 Aug 2026. 8 days.**
Test set (71 questions) has been out since 5 Aug. 5 submissions/day allowed.

This replaces the v1 design doc. v1 was a reasonable sketch of *a* pipeline; it was
not written against the actual scoring code, and three of its choices would have
cost us the competition outright. Everything below is grounded in `scripts/evaluate.py`,
`scripts/validate_submission.py`, `schema/submission.schema.json`, and measurements
on the 55 gold validation records.

---

## 0. Corrections to v1 (read first)

| v1 said | Reality | Cost if shipped |
|---|---|---|
| `answer.multiple_choice = {"label": "C"}` | Evaluator reads `.gold`; validator **rejects** any key but `gold` | **Submission invalid.** 0 on the biggest answer metric |
| Freeform is the main answer target | Test set is **50 MC + 21 table, zero freeform** | Weeks spent optimising a metric that isn't scored |
| Evidence locator carries `row`/`column` | Submission schema is `additionalProperties: false`; only `page`, `table_id`, `figure_id`, `section`, `equation_id`, `algorithm_id`, `citation_id` allowed | Submission invalid |
| "fuzzy title match is your primary tool" | 7.5% of pool titles are **space-mangled**; the papers questions ask about are often named by an acronym absent from title *and* abstract | Silent recall ceiling ~50% on `multi_paper` |
| Fetch PDFs from `pdf_url` | OpenReview (12,035 papers, 44% of pool) returns **403 Challenge verification required**; `arxiv_id` and `doi` are **null for all 27,487 rows** | No PDF for the venues that dominate gold |
| GROBID for references | Useful, but the coarse evidence key only needs `citation_id` + `page` | Infra cost with no scoring return |

---

## 1. The scoring function, exactly

From `evaluate.py`. Every design decision below follows from this.

**Per question**, macro-averaged over all questions:

```python
prf(gold_set, pred_set)   # precision, recall, F1
  gold and pred both empty -> (1, 1, 1)
  pred empty, gold non-empty -> (0, 0, 0)
  gold empty, pred non-empty -> (0, 1, 0)      # over-predicting is punished
```

**Papers.** `paper_f1_macro` over `{paper_id}` sets. Precision counts — a shotgun
of 20 candidates scores worse than 3 good ones.

**Evidence.** Sets of the coarse 4-tuple:

```python
(paper_id, source_type, str(locator.page or locator.section), object_id)

object_id = normalize_visible_id(...)   # lowercased, "Table 4" -> "table 4"
  table              -> locator.table_id
  figure             -> locator.figure_id
  equation_algorithm -> locator.equation_id or locator.algorithm_id
  citation_context   -> locator.citation_id
  text_span          -> ""   (always)
```

Consequences worth internalising:
- `row`, `column`, `region`, `paragraph_id`, `sentence_start/end` are **ignored**.
  Gold carries them; we must not emit them (schema rejects them) and we don't need them.
- **`text_span` needs only the right page.** `object_id` is always `""`, and
  `location` takes `page` before `section`. Cheapest evidence type to get right.
- `citation_id` may be emitted as `"24"` or `"Citation 24"` — both normalise to
  `"citation 24"`. Gold uses bare integers.
- An evidence item missing `page`/`section` **and** an object id is silently dropped
  from the set. Dropping costs recall but not precision.

**Answers.**
- `multiple_choice_accuracy` — exact label match on `answer.multiple_choice.gold`.
- `freeform_exact_match` — **exact string match** after lowercase + whitespace
  collapse + quote strip. Not fuzzy, no LLM judge. *Not present in the test set.*
- `table_row_f1_macro` — F1 over row-key tuples (columns with `is_row_key: true`,
  else first column), normalised the same way.
- `table_cell_accuracy_*` — over non-row-key columns, only for gold rows whose key
  we matched. Numbers compare with `math.isclose(rel_tol=1e-6)`; a missed row key
  zeroes every cell in that row.

### 1.1 What the test set actually asks for

| | count | scored metrics |
|---|---|---|
| MC only | 50 | paper F1, evidence F1, MC accuracy |
| table only | 21 | paper F1, evidence F1, table row F1 + cell accuracy |
| freeform | **0** | — |

**Optimisation order: paper F1 → evidence F1 → MC accuracy → table.** Paper and
evidence F1 are scored on all 71; MC on 50; table on 21. Paper retrieval is also
a hard prerequisite for the other two, so it is the top priority twice over.

---

## 2. Measured facts about the data

Everything here is reproducible from `exp/`.

### 2.1 Titles are space-mangled (7.5% of the pool)

```
"500xCompressor"  is stored as  "500x C ompressor"
"AceMath"         is stored as  "A ce M ath"
"100-LongBench"   is stored as  "100- L ong B ench"
```
Questions use the normal spelling. Token matching and `rapidfuzz` both fail here.
**Fix:** `squash()` — lowercase alphanumerics only — makes both spellings identical.
The nickname index is built over squashed joins of 1–4 *adjacent title tokens*, so
`"ace"+"math" -> "acemath"` matches while short acronyms still respect word
boundaries. (`littraceqa/textnorm.py`, `retrieval/lexical.py`.)

### 2.2 `multi_paper` gold sets are topical clusters, not answer sets

The single most important discovery. 55 validation questions map to only **33
distinct gold paper-sets**; one 4-paper cluster is shared by **12 questions**:

```
q_028 q_029 q_031 q_032 q_033 q_034 q_035 q_036 q_039 q_040 q_041 q_042
   -> Truncated Consistency Models              (iclr2025_03463)
      Inductive Moment Matching                 (icml2025_01371)
      Simplifying, Stabilizing and Scaling CMs  (iclr2025_03031)
      Consistency Models Made Easy              (iclr2025_00615)
```

`evidence_papers ⊆ gold_papers` always, and for 6 of 29 `multi_paper` questions
the evidence lives in **one** paper while gold lists **four**. So gold is the
*comparison set the question is drawn from*, and the sibling papers are graded
even though they contain no evidence.

Payoff: on a 4-paper cluster, returning only the answer-bearing paper scores
F1 = 0.40; returning the cluster scores 1.00. **Cluster expansion is worth ~0.6 F1
on 53% of questions.** This is entity set expansion, not retrieval — see §4.3.

Gold-set sizes: 26×1, 1×3, 27×4, 1×9. `multi_paper` is almost always exactly 4.
Test questions frequently state the size in words ("the **two** ICCV 2025 papers"
— 24 of 71), which is a usable but noisy signal: a naive count-word regex scores
0/3 on validation because the counts refer to methods, not papers. Require the
count word to govern "paper(s)/work(s)/studies".

### 2.3 Papers are named by acronyms absent from title and abstract

`IMM`, `TCM`, `MoD`, `sCT`, `ECM`, `VTI` appear nowhere in the metadata of their
own papers. Several are initialisms of the title:

```
IMM -> Inductive Moment Matching       TCM -> Truncated Consistency Models
MoD -> Mixture of Decoding
```

`retrieval/acronym.py` enumerates plausible initialisms per title (all-word and
content-word initials, over every prefix of the pre-subtitle head) and indexes
them. Recovers IMM/TCM/MoD; the rest arrive via cluster expansion.

### 2.4 PDF availability (measured, not assumed)

| venue | papers | source | status |
|---|---|---|---|
| CVPR, ICCV | 5,572 | openaccess.thecvf.com | ✅ 200 |
| ACL, EMNLP, NAACL | 7,493 | aclanthology.org | ✅ 200 |
| ECCV | 2,387 | ecva.net | ✅ 200 |
| ICML 2025 | 3,046 | ⚠️ openreview 403 → **PMLR v267** | ✅ mirror confirmed |
| NeurIPS 2025 | 5,286 | ⚠️ openreview 403 → **papers.nips.cc/paper_files/paper/2025** | ✅ mirror confirmed (5,823 entries) |
| ICLR 2025 | 3,703 | ⚠️ openreview 403 | **needs authenticated OpenReview session** |

`arxiv_id` and `doi` are null for every row, so there is no metadata-level fallback.
ICLR is the one real gap and it matters: ICLR supplies 55 of 146 validation gold
papers. **Action: authenticated `openreview-py` client** (free account, official
API). arXiv title-match is the degraded fallback — it recovers the paper and the
answer but shifts page numbers, so evidence F1 on those questions drops.

### 2.5 Free-tier model budget

Gemini free tier is the strongest free option and the only one with **native PDF
input + vision + 1M context**, which is exactly this task's shape. Groq and
Cerebras are text-only but fast and useful for cheap classification. Plan around
~250–1,000 requests/day on the vision model.

**Architectural consequence: all high-volume work must be local.** Retrieval over
27,487 papers, PDF parsing, and page selection run on the RTX 4080 / 32 cores with
no API calls. The API is spent only on the low-volume, high-value step — reading a
specific paper to produce the answer and its locator. Budget ≈ 71 questions ×
(2–4 papers) × (1–2 calls) ≈ 300 calls per full test run, which fits one day's quota.

---

## 3. Prior art this problem decomposes into

The task is not novel end-to-end, but each stage is a well-studied problem. Where
we borrow from, and what we take:

| stage | field | what we take |
|---|---|---|
| Nickname → paper | **Entity linking / abbreviation expansion** (Schwartz–Hearst) | Generate candidate initialisms from titles instead of mining `(ABBR)` from text |
| Mangled titles | **Record linkage / blocking** (Fellegi–Sunter, dedup literature) | Canonical squashed blocking key; compare on the key, not the surface form |
| Candidate generation | **Hybrid IR** (BEIR, TREC-DL) | BM25 + dense, fused by **RRF** — no score calibration needed across signals |
| Ranking | **Cross-encoder reranking** (MS MARCO) | Local reranker over top-40; cheap and reliably worth several points |
| Cluster recovery | **Entity set expansion** (Google Sets, SEISA) | Seed = confidently-retrieved paper; expand via kNN in embedding space, filter for set coherence |
| Multi-hop chains | **HotpotQA / MuSiQue / IIRC** | Explicit query decomposition; one sub-question per hop rather than one giant prompt |
| Evidence grounding | **QASPER, SciFact, FEVER** | QASPER is the closest analogue — QA over papers with an evidence-F1 metric. Take: retrieve-then-select, and *abstain* rather than guess when confidence is low (precision is graded) |
| Figure/equation reading | **DocVQA, ChartQA, InfographicVQA** | Render the page and ask a VLM; do not trust text extraction on dense layouts |
| Table reading | **FinQA, TAT-QA, TabFact** | Answer-normalisation discipline for exact-match numerics |
| MC answering | **Self-consistency** (Wang et al.) | k-sample majority vote; the cheapest accuracy point available |
| Output shape | **Constrained decoding** | Validate against the JSON schema in-loop, repair, never emit free text |

---

## 4. Architecture

Five stages. Each has **≥2 implementations** so the ablation harness (§6) can pick
per-stage winners on validation rather than by argument.

```
question
  │
  ├─ A. Mention & scope extraction ────── nicknames, venue/year, expected set size
  │
  ├─ B. Candidate generation (local, free)
  │      nickname n-gram · acronym · BM25 · dense — fused by RRF, per mention
  │
  ├─ C. Ranking + cluster expansion ───── cross-encoder rerank → seed → kNN expand
  │        └─> gold_papers
  │
  ├─ D. Evidence localisation ─────────── PDF fetch → page shortlist → VLM read
  │        └─> evidence[]
  │
  └─ E. Answer synthesis ──────────────── MC vote / table build → schema validate
           └─> answer{}
```

### 4.1 Stage A — mention & scope

- **A1 (built)** regex extractor: CamelCase, acronyms incl. 2-char, hyphen-caps,
  quoted spans, `"the X paper"`, `"introduces X"`.
- **A2** LLM extractor: one cheap call returning `{mentions, venues, years, n_papers}`.
- **A3** union of A1 ∪ A2 (expected winner — A1 is high-recall and free, A2 catches
  purely descriptive references like *"the topology-aware node description synthesis
  method"* that A1 cannot see).

Scope is applied **softly** (boost, not filter): 24/71 test questions name a venue,
but questions like *"Across all venues, ..."* exist and a hard filter that guesses
wrong is unrecoverable.

### 4.2 Stage B — candidate generation *(local, no API)*

Signals, each run **per mention** and once for the whole question, fused by RRF
(`k=60`). Per-mention retrieval is what makes multi-paper work: scoring the whole
question as one query buries the second paper.

- **B1** nickname n-gram index (squashed, 1–4 adjacent title tokens) — highest precision
- **B2** acronym index (§2.3)
- **B3** BM25 over title + 2×title + abstract
- **B4** dense bi-encoder over title+abstract (local GPU; BGE / E5 / Qwen3-Embedding)
- **B5** B1+B2+B3 (no GPU needed) vs **B6** all four

Measured so far (validation, recall of gold papers):

| config | recall@40 | single-paper | multi-paper |
|---|---|---|---|
| BM25 only, question as query | 67.0% @50 | — | — |
| B1+B3 RRF, per-mention | 68.5% | **96.2%** | 43.7% |

Single-paper retrieval is effectively solved. **Every remaining point is in
`multi_paper`, and §2.2 says the fix is expansion, not better search.**

### 4.3 Stage C — ranking + cluster expansion

- **C1** RRF score only (baseline).
- **C2** cross-encoder rerank of top-40 on `(question, title+abstract)`, local GPU.
- **C3** **cluster expansion** — the high-value one. Take the top-1 reranked paper
  as seed, pull its k nearest neighbours in embedding space, keep those that are
  coherent with the question's scope, emit the top-n set.
- **C4** C2 → C3 → LLM set-verification: show the LLM the candidate set and the
  question, let it drop members that don't belong.

Set size n: from the question when it governs "papers" (§2.2), else the learned
prior (1 for single-paper, 4 for multi-paper), with the family predicted by a
cheap classifier. **This is the biggest single lever in the whole system — tune n
against validation `paper_f1_macro` directly, since the F1 trade-off is explicit.**

### 4.4 Stage D — evidence localisation

Fetch (`pdf/fetch.py`, per-venue routing + mirrors from §2.4, cache by `paper_id`,
never re-download), then:

- **D1** text-only: PyMuPDF page text → LLM picks page + object id.
- **D2** vision: render candidate pages at 2× → VLM reads them.
- **D3** native PDF upload: hand the whole PDF to Gemini, ask for answer + page +
  object id in one call. Fewest calls, uses the 1M context, no page-shortlisting
  bug surface. **Expected winner on call budget.**
- **D4** D1 to shortlist 3 pages → D2 to read them (highest fidelity, most calls).

Locator emission is mechanical once the object is identified, and cheap wins exist:
`text_span` needs only the page; a `table`/`figure` id is a caption regex away
(`^(Table|Figure)\s+(\d+)` over page text) and can be **cross-checked against the
VLM's answer** rather than trusted from either source alone.

Abstention policy: emit evidence only above a confidence threshold. Gold evidence
sets are small (1–4 items); a wrong extra item costs precision on a macro-averaged
metric. Tune the threshold on validation.

### 4.5 Stage E — answer synthesis

- MC: **self-consistency**, k samples → majority vote over labels. Always emit a
  label; there is no abstention credit and a blind guess is worth 0.25.
- Table: build rows from the question's `table_schema`. **Free win** — when the
  row key is a paper-title column, gold row values are the metadata `title`
  field *verbatim*, HTML entities and all (verified on q_020, q_023). Emit
  `pool[paper_id].title` unmodified and row F1 tracks paper F1 exactly.
  For other row keys (`dataset`, `metric`, `quantity`), the keys are usually
  enumerable straight from the question text — extract them first, fill cells second.
- Every record goes through `schema/submission.schema.json` **and** the official
  `validate_submission.py` before it is written.

---

## 5. Repository layout

```
littraceqa/
  textnorm.py            squash / demangle / clean          [done]
  corpus.py              pool, Question, Paper, io          [done]
  retrieval/
    lexical.py           BM25 + nickname n-gram index       [done]
    acronym.py           title-initialism index             [done]
    scope.py             venue/year extraction              [done]
    hybrid.py            per-mention RRF fusion             [done]
    dense.py             bi-encoder + kNN                   [next]
    expand.py            cluster expansion                  [next]
  pdf/
    fetch.py             per-venue routing + mirrors        [next]
    read.py              PyMuPDF text/render, caption regex [next]
  reason/
    client.py            provider-agnostic LLM client, cache, retry
    localize.py          evidence localisation D1–D4
    solve.py             MC / table answering
  answer/
    build.py             schema-exact record construction
    validate.py          in-process validator
exp/                     numbered, reproducible experiments
reports/                 ablation results, committed
scripts/                 official evaluate.py / validate_submission.py (unmodified)
```

## 6. Ablation harness

`exp/run_ablation.py --stage {A,B,C,D,E} --configs ...` runs each variant over
validation, writes `reports/<stage>.json`, and prints the official metrics plus
the **per-evidence-type breakdown** (table / figure / text_span / citation_context
/ equation_algorithm) and per-`task_family` split. Configuration is a dict, not a
code edit, so every number in the system paper is reproducible by flag.

Guardrail: 55 validation questions is a small sample — a 2-point difference is
noise. Report bootstrap CIs and prefer the simpler config on ties. Do not tune
the abstention threshold to three decimal places on 55 examples.

## 7. Schedule

| day | deliverable | gate |
|---|---|---|
| 11 Aug | scoring reverse-engineered, retrieval measured, plan | ✅ done |
| 12 Aug | dense + rerank + cluster expansion; PDF fetcher w/ mirrors | paper F1 ≥ 0.75 on validation |
| 13 Aug | evidence localisation D1–D4, ablate | evidence F1 ≥ 0.45 |
| 14 Aug | MC + table synthesis, full pipeline, **first test submission** | valid submission on the board |
| 15–17 Aug | ablate, fix weakest evidence type, self-consistency, expansion tuning | daily submission, monitor |
| 18 Aug | freeze best config, full rerun, `test_extra` diagnostics for the paper | — |
| 19 Aug | final submission early in the day (AoE deadline) | — |

**Submit something valid by 14 Aug.** 5 submissions/day is ample, but a
malformed-submission discovery on the 19th is unrecoverable.

## 8. Open items

1. **OpenReview credentials** — needed for 3,703 ICLR PDFs. Put
   `OPENREVIEW_USERNAME` / `OPENREVIEW_PASSWORD` in `.env` (gitignored).
2. **Gemini API key** — `GEMINI_API_KEY` in `.env`. Free tier, no card.
   Optional: `GROQ_API_KEY`, `CEREBRAS_API_KEY` for cheap text-only stages.
3. **Team name** — one immutable name per HF account, and it must match across
   the evaluator, the system paper, and OpenReview. Decide before first submission.
