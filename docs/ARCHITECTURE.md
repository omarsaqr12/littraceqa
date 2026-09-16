# System architecture

LitTraceQA is a *research pipeline*, not a hosted service. The supported entry point is [`run.py`](../run.py), which parses CLI flags, loads the corpus and split, constructs the configurable [`Pipeline`](../littraceqa/pipeline.py), runs questions, and writes a schema-shaped JSONL submission. The data and pretrained models are not packaged in this repository.

```text
question + 27,487-paper metadata pool
   │
   ├─ A. mention and venue/year scope extraction
   │       retrieval/lexical.py · retrieval/acronym.py · retrieval/scope.py
   ├─ B. candidate retrieval
   │       BM25 / nickname n-grams / optional dense embeddings → hybrid RRF
   │       retrieval/hybrid.py · retrieval/dense.py
   ├─ C. paper selection
   │       cross-encoder reranker → optional LLM shortlist selector
   │       or mention-anchored/fused selection; experimental expansion is off
   │       retrieval/rerank.py · retrieval/verify.py · retrieval/select.py
   ├─ D. PDF grounding (network / external model-dependent)
   │       fetch & cache PDF → enumerate page/figure/table/equation objects
   │       → paper reader returns answer candidates and evidence locators
   │       pdf/fetch.py · pdf/objects.py · reason/localize.py
   ├─ E. answer synthesis
   │       multiple-choice/table/freeform synthesis; optional visual cell fill
   │       reason/solve.py · answer/table_visual.py
   └─ submission builder + schema validator → JSONL
           answer/build.py · scripts/validate_submission.py
```

This diagram is a *source-code map*, not a verification claim. Each stage has swappable configurations in `PipelineConfig`. The code labels stages A–C as local paper selection; using `--llm-select` changes that cost boundary because an external or locally served LLM may then participate in paper selection. The PDF reader and answer synthesis can also consume hosted API calls. Do not infer that all retrieval modes are key-free or that a no-key run reproduces the reported best result.

## Follow a question through the code

| What to inspect | Starting point | Important contract or failure mode |
| --- | --- | --- |
| Input fields, paper metadata and JSONL I/O | [`littraceqa/corpus.py`](../littraceqa/corpus.py) | Split files live under `data/`; no dataset files are vendored. |
| Nickname/title correction | [`littraceqa/textnorm.py`](../littraceqa/textnorm.py) | Title normalization can change candidate recall and must be evaluated against real pool titles. |
| Candidate generation | [`littraceqa/retrieval/hybrid.py`](../littraceqa/retrieval/hybrid.py) | Retrieval recall constrains all later stages; successful reranking cannot recover absent papers. |
| Candidate selection | [`Pipeline.select_papers`](../littraceqa/pipeline.py) | `use_llm_selector` is opt-in; disabled experiments such as title pinning and expansion are retained for provenance. |
| PDF download and locator enumeration | [`littraceqa/pdf/fetch.py`](../littraceqa/pdf/fetch.py), [`littraceqa/pdf/objects.py`](../littraceqa/pdf/objects.py) | PDF access, page alignment and object identifiers can fail independently of correct paper selection. |
| Hosted and local clients | [`reason/client.py`](../littraceqa/reason/client.py), [`reason/local_client.py`](../littraceqa/reason/local_client.py), [`reason/local_llm.py`](../littraceqa/reason/local_llm.py) | Check model version, rate limits, cache keys and timeouts before interpreting a comparison. |
| Result construction | [`littraceqa/answer/build.py`](../littraceqa/answer/build.py) | The final record must match each question's requested answer types and evidence schema. |
| Score interpretation | [`scripts/evaluate.py`](../scripts/evaluate.py), [`reports/endgame.md`](../reports/endgame.md) | Arithmetic consistency is not experimental replication or independent verification of hidden-test labels. |

The runner keeps paper selection even when a PDF/LLM stage fails; see `Pipeline.run_question` and its trace fields (`fetch_failures`, `read_error`, `answer_error`). That is a useful fault-containment decision, but empty or fallback answers can still satisfy a schema while scoring badly. Read error counters and traces before comparing scores. The tracked validator contains an extra all-null table-row safeguard; it is **not identical** to a pristine organizer validator.

## Where the research evidence lives

- [`exp/`](../exp/) has numbered exploratory experiments and an ablation runner; see the [experiment index](EXPERIMENT_INDEX.md) for an entry-point map. They are historical scripts, not a permanently maintained test suite.
- [`reports/`](../reports/) documents positive, negative and retracted findings, including selection, table, evidence and scorer analyses. When reports disagree, use dates, matching-control configurations and the later correction rather than selecting the most favorable number.
- [`results/`](../results/) holds a partial evaluator export, score ledger and arithmetic consistency code. The historical best submission is in [`submission/`](../submission/); it includes manual auditing and leaderboard feedback.
- [`paper/`](../paper/) holds the final system-paper PDF and source as well as archived submission notes. Preserve these submission artifacts when reorganizing documentation.

For environment setup and a carefully bounded reproduction claim, read [REPRODUCIBILITY.md](REPRODUCIBILITY.md).
