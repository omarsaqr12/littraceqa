# LitTraceQA — literature-grounded question answering

**Team OdeD · GroundLM 2026 shared task · Omar Saqr and Mostafa Gaafar (The American University in Cairo)**

A research pipeline for answering questions about scientific papers. It finds relevant work in a **27,487-paper pool**, reads the source PDFs for specific evidence, and returns multiple-choice answers or schema-constrained tables with paper IDs and evidence locators. The engineering challenge is not just generating an answer: **paper selection, evidence identification, and the exact evaluator schema all affect the result**.

**Explore the project:** [System paper (PDF)](paper/littraceqa_system.pdf) · [Source code](littraceqa/pipeline.py) · [Architecture](docs/ARCHITECTURE.md) · [Experiment index](docs/EXPERIMENT_INDEX.md) · [Reproducibility](docs/REPRODUCIBILITY.md) · [Scoring records](results/official_scores.csv).

## Results, with the necessary distinction

| Historical shared-task run | Reported official overall score | Interpretation |
| --- | ---: | --- |
| First submission | 0.4563 | Initial submission |
| Best **fully automated** run | **0.5519** | The automated pipeline, without per-question auditing |
| Best submitted artifact | **0.7649** | Included manual source-PDF checks and leaderboard-feedback attribution; **not** autonomous performance or an estimate of generalization |

The submitted [JSONL artifact](submission/littraceqa-test_OdeD.jsonl), [system paper](paper/littraceqa_system.pdf), and [scoring analysis](reports/scoring_and_fixes.md) document the distinction. These numbers are historical official results reported in the repository; this portfolio review did **not** independently reproduce the hidden-test evaluation. Comparing 0.7649 with another system's unattended score as if both were automatic would be misleading.

## What we built

```text
Question + paper metadata
    → normalize title/mention cues and extract scope
    → BM25 + nickname/acronym + optional dense candidates
    → hybrid ranking + cross-encoder reranking
    → optional LLM shortlist selection
    → retrieve PDFs and enumerate possible evidence locators
    → read selected papers; synthesize multiple-choice or table answers
    → schema-exact JSONL + submission validation
```

The orchestrator is [`littraceqa/pipeline.py`](littraceqa/pipeline.py); [`run.py`](run.py) exposes the stages as CLI options. Failed PDF or model calls can leave paper-selection output intact, which makes partial failures diagnosable, but they do not magically produce correct answers. The code includes both hosted and local-model interfaces; model availability, API limits and PDF access change which configurations can run. The [architecture guide](docs/ARCHITECTURE.md) links each stage to the actual modules and explains those boundaries.

**Engineering and research contributions visible in the repository:** a configurable retrieval-to-answer pipeline; locator-aware PDF reading; schema-constrained answer construction; local and hosted model adapters; an ablation harness; and reports that preserve negative results, retractions and error diagnoses. Individual ownership of particular components is not established by repository ownership; this was a two-person team project.

## A useful no-key inspection path

No API key, GPU or dataset download is needed to read the [paper](paper/littraceqa_system.pdf), browse the [experiment index](docs/EXPERIMENT_INDEX.md), or inspect the [scored submission records](results/official_scores.csv). With Python 3, you can also check the arithmetic of the retained scoring components:

```bash
python3 results/validate_table3.py
```

That script reports which rows can be checked, compares recomputed overall values within the documented rounding tolerance, and writes `results/table3_validation.csv` / `.json`. It **does not** run the model, re-score the prediction JSONL against hidden gold, or independently authenticate leaderboard values. The retained evaluator export is partial. Run this on a disposable checkout if you do not want to modify committed outputs.

## Set up and run the research pipeline

A Linux environment is recommended, but a fresh-checkout end-to-end installation and execution have **not** been verified as part of this portfolio review. This project may need large pretrained model downloads, PDF network access, GPU resources and hosted-model API quota. Review the [reproducibility guide](docs/REPRODUCIBILITY.md) before a costly full run.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/download_data.sh
cp .env.example .env  # put your own API credentials here; do not commit .env

# Retrieval-only path: no hosted LLM key, but local model downloads may occur.
.venv/bin/python run.py --split validation --no-read \
  --out preds/val_retrieval.jsonl

# Historical full-pipeline configuration; requires external services and PDFs.
.venv/bin/python run.py --split test --llm-select --visual-table \
  --max-papers 3 --mc-samples 1 --rpm 14 --out preds/test.jsonl

# Validate output format against the downloaded inputs and paper metadata.
.venv/bin/python scripts/validate_submission.py \
  --input data/test.jsonl --pred preds/test.jsonl
```

The dataset is separately hosted under **CC BY-NC 4.0** and is not committed here. [`scripts/download_data.sh`](scripts/download_data.sh) fetches upstream files without a pinned revision; save hashes for rigorous reproduction. It does not overwrite the repository's modified validator; `--organizers` optionally downloads pristine organizer scripts into `scripts/organizers/`. Historical GPU runs used PyTorch `2.6.0+cu124`, whereas [`requirements.txt`](requirements.txt) pins the plain `2.6.0` package. Pre-cache the embedding and reranker models: the per-question watchdog can otherwise interrupt a first-time download. See [data setup](data/README.md) for the exact fetched-file manifest.

**None of the commands above is being represented as an audit-passed end-to-end run.** The code's submission validator verifies shape and known paper IDs; passing it alone does not establish answer correctness.

## Research findings: follow evidence, including what failed

The evaluator combines paper F1, evidence F1 and an answer composite; its locally implemented formula is:

```python
answer = (multiple_choice_accuracy + table_row_f1_macro + table_cell_accuracy_macro) / 3
overall = (paper_f1_macro + evidence_f1_macro + answer) / 3
```

The individual contributions to overall are therefore `1/3, 1/3, 1/9, 1/9, 1/9` for paper F1, evidence F1, multiple choice, row F1 and cell accuracy. These *metric-component* weights are not interchangeable with per-question weights; read the [scorer derivation](reports/endgame.md) before interpreting an experiment.

| Investigation | What the records show | Read the evidence |
| --- | --- | --- |
| Paper selection | LLM shortlist selection was a measured gain; generating paper titles outright was not a viable substitute for candidate retrieval. | [Paper selection](reports/paper_selection.md) · [Experiments 12–13](docs/EXPERIMENT_INDEX.md) |
| Table grounding | Rendering the table helped cell prediction in a validation comparison, but did not transfer as a test gain; row keys needed separate handling. | [Table stage](reports/table_stage.md) |
| Evidence and formatting | Page offsets, locator types, row labels and null-cell conventions affect the recorded scorer outcome. | [Evidence measurements](reports/e4_e6_measurements.md) · [Scoring and fixes](reports/scoring_and_fixes.md) |
| Negative results and corrections | Several heuristics were rejected. An early free-selector comparison was **retracted** after rate-limit errors contaminated the result. | [Free selectors and evidence](reports/free_selectors_and_evidence.md) · [Hypotheses](HYPOTHESES.md) |
| Validation vs. test | The splits have different question regimes; a validation improvement is not automatically a hidden-test improvement. | [Leaderboard gap](reports/leaderboard_gap.md) · [Endgame](reports/endgame.md) |

These are the team's recorded findings, not newly rerun measurements. The experiment index links **all 22 numbered scripts plus the ablation runner**. Preserve the negative results and corrected conclusions when citing this work.

## Repository guide

| Path | Purpose |
| --- | --- |
| [`littraceqa/`](littraceqa/) | Retrieval, PDF processing, model clients, reasoning and answer construction |
| [`exp/`](exp/) | 23 historical experiment entry points; not a maintained CI test suite |
| [`reports/`](reports/) | Per-stage analysis, measurement limitations, retractions and manuscript audits |
| [`results/`](results/) | Partial evaluator log, official score records and arithmetic cross-check |
| [`paper/`](paper/) | [Paper PDF](paper/littraceqa_system.pdf), LaTeX, bibliography and figure generator; its README is archived pre-camera-ready guidance |
| [`submission/`](submission/) | Historical submitted output, including the manually audited best submission |
| [`scripts/`](scripts/) · [`schema/`](schema/) | Dataset tools, evaluator, modified submission validator and schemas |
| [`docs/`](docs/) | [Architecture](docs/ARCHITECTURE.md), [reproducibility](docs/REPRODUCIBILITY.md), [experiments](docs/EXPERIMENT_INDEX.md) |

## Limitations, attribution and license

The manually audited best submission is not evidence of generalizable unattended accuracy. The public dataset, source PDFs, API model versions and quotas, and evaluation-specific conventions limit reproducibility. The [system paper](paper/littraceqa_system.pdf) discusses the methodology and limitations. **Omar Saqr and Mostafa Gaafar** are the team authors; this README does not claim sole authorship or invent a division of labor. The repository [LICENSE](LICENSE) covers repository content as written; third-party datasets, model weights and source PDFs have their own terms.
