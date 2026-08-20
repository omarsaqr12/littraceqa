# Exactly what to submit --- OpenReview, GroundLM 2026

Portal: <https://openreview.net/group?id=EMNLP/2026/Workshop/GroundLM>
Deadline: **19 August 2026, AoE** (= 20 Aug 12:00 UTC)

---

## 1. Form fields (copy verbatim)

**Title**
```
OdeD at GroundLM 2026 Shared Tasks: Reading the Scorer for Literature-Grounded QA
```

**teamname** (must be identical to the evaluator registration)
```
OdeD
```

**Authors** --- in this order
| name | email | affiliation |
|---|---|---|
| Omar Saqr | `omar_saqr@aucegypt.edu` | The American University in Cairo |
| Mostafa Gafaar | `mostafa21314@aucegypt.edu` | The American University in Cairo |

**Abstract** --- paste from `paper/openreview_abstract.txt` (plain text, no LaTeX)

**Keywords** (if the field appears)
```
literature-grounded question answering; evidence grounding; scientific document understanding; shared task; error analysis; negative results
```

---

## 2. Files to attach

| # | file | what it is |
|---|---|---|
| 1 | `paper/littraceqa_system.pdf` | the system paper --- 8 pages, 7 main + references |
| 2 | the JSONL you uploaded to `littraceqa-test` that produced the reported score | required: "the JSONL test-output files uploaded to the evaluator" |
| 3 | code / reproducibility materials | see below |

**Which JSONL.** The paper reports **0.7649**. That is the submission whose
evaluator output was `evidence_f1 0.731858`, `row_f1 0.499206`. Attach that exact
file. If a later submission scored higher, tell me and I will update the paper
before you attach anything --- the reported number and the attached file must be
the same run.

**Code.** Either give the repo URL
```
https://github.com/omarsaqr12/littraceqa
```
(make it public, or invite the organisers) **or** attach a zip of the repo
excluding `pdf_cache/`, `cache/` and `.env`. It contains the pipeline, the five
automated verifiers, the experiment scripts, and the reports recording every
measurement including the negative ones.

---

## 3. External resources to declare

The organisers ask you to "clearly disclose external datasets, pretrained models,
tools, APIs, and generated or synthetic data". Section 9 of the paper does this
in full. If the form has a separate field, the short version is:

* **Data** --- released LitTraceQA metadata pool (27,487 papers), dev split (55),
  input-only test split (71), CC BY-NC 4.0. PDFs fetched from the publisher URLs
  in the released metadata. **No additional annotated data. No synthetic data.**
* **Models / APIs** --- Google Gemini (`gemini-flash-lite-latest` and siblings,
  free tier); Qwen3 served locally via an OpenAI-compatible `llama.cpp` endpoint;
  a cross-encoder reranker and a sentence embedding model for retrieval;
  Anthropic Claude as the agent performing the per-question audit.
* **Tools** --- Python, PyMuPDF, and the organisers' released `evaluate.py` and
  `validate_submission.py`.
* **Training** --- none. We fine-tuned nothing.

---

## 4. Before you click submit

- [ ] Re-run **ACL PubCheck** on the current PDF (a figure was added since your run)
- [ ] Title, `teamname` and evaluator registration all read exactly `OdeD`
- [ ] Both author emails correct
- [ ] The attached JSONL is the run whose score the paper reports
- [ ] Code URL is reachable by the organisers, or the zip is attached
