# LitTraceQA | Literature-grounded question answering

**GroundLM 2026 shared task · Team OdeD · Omar Saqr and Mostafa Gaafar, The American University in Cairo**

LitTraceQA is a research system for answering questions about scientific papers. Given a question and a **27,487-paper metadata pool**, it retrieves candidate papers, reads relevant PDFs, identifies supporting evidence, and outputs multiple-choice answers or structured tables in the shared task's exact submission format. The challenge spans **retrieval, document understanding, grounded answer construction, and evaluation**, not just text generation.

[Read the system paper](paper/littraceqa_system.pdf) · [Explore the pipeline](littraceqa/pipeline.py) · [Architecture](docs/ARCHITECTURE.md) · [Experiment index](docs/EXPERIMENT_INDEX.md) · [Reproducibility](docs/REPRODUCIBILITY.md) · [Submission artifact](submission/littraceqa-test_OdeD.jsonl)

## Project highlights

| Area | What the repository contains |
| --- | --- |
| Retrieval | BM25, title/nickname and acronym matching, optional dense retrieval, hybrid ranking and cross-encoder reranking |
| PDF grounding | Paper fetching, page/table/figure locator enumeration and evidence-linked reading |
| Answer generation | Hosted/local model interfaces, multiple-choice and schema-constrained table construction |
| Experimental rigor | Configurable ablations, retained scoring records, negative results, corrections and a documented split between automatic and manually audited submissions |

The complete flow is implemented in [`littraceqa/`](littraceqa/) and driven by [`run.py`](run.py). The [architecture guide](docs/ARCHITECTURE.md) is a source-linked map from each stage to its implementation. This was a **two-person team project**; repository ownership is not evidence of exclusive authorship of individual modules.

## Results and evaluation context

| Historical shared-task result | Reported overall score | What was evaluated |
| --- | ---: | --- |
| Initial submission | 0.4563 | First submission |
| Best fully automated run | **0.5519** | Pipeline output without per-question human auditing |
| Best submitted artifact | **0.7649** | Submission with manual source-PDF auditing and leaderboard-feedback attribution |

**0.7649 is not autonomous model performance.** The [system paper](paper/littraceqa_system.pdf), [scoring analysis](reports/scoring_and_fixes.md), [submission JSONL](submission/littraceqa-test_OdeD.jsonl), and [retained official-score ledger](results/official_scores.csv) document the results and interventions. The scores are historical reported results, not an independently rerun hidden-test evaluation; the manually audited score should not be compared directly with an unattended system's score.

## How it works

```text
Question + paper metadata
  → extract mentions, title cues and scope
  → retrieve lexical / acronym / optional dense candidates
  → hybrid ranking + cross-encoder reranking
  → optionally select a paper shortlist with an LLM
  → fetch PDFs and enumerate evidence locators
  → read selected papers and construct answers
  → validate schema-exact JSONL predictions
```

[`Pipeline`](littraceqa/pipeline.py) exposes interchangeable stages and records per-question failures; a PDF or model failure need not erase already retrieved paper IDs. [`littraceqa/retrieval/`](littraceqa/retrieval/) handles candidate generation and selection, [`littraceqa/pdf/`](littraceqa/pdf/) handles source documents, [`littraceqa/reason/`](littraceqa/reason/) handles readers and answer synthesis, and [`littraceqa/answer/`](littraceqa/answer/) builds structured outputs. A schema-valid fallback can still be wrong, so traces and missing-evidence counts matter. See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for module-level details and cost boundaries.

## Explore the work in five minutes

You can inspect the [paper](paper/littraceqa_system.pdf), [experiment index](docs/EXPERIMENT_INDEX.md), [research reports](reports/), and [results](results/) **without an API key, GPU, or dataset download**. With Python 3, run a local check of the *retained score arithmetic*:

```bash
python3 results/validate_table3.py
```

This recomputes overall values from recorded component scores and reports uncheckable rows; it **does not** rerun the model or authenticate hidden-test labels. The export is partial, and the script writes CSV/JSON files under `results/`, so use a disposable checkout if you want to avoid changing tracked outputs. The [reproducibility guide](docs/REPRODUCIBILITY.md) explains the evidence levels.

## Run the research pipeline

A Linux environment is recommended. A full fresh-checkout pipeline run was not independently reproduced during repository cleanup; pretrained-model downloads, source PDFs, hosted API quotas, and GPU requirements depend on the configuration. Review [REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) before running the full split.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/download_data.sh
cp .env.example .env   # add your own keys; never commit .env

# Retrieval-only run: no hosted LLM key; local model downloads may occur.
.venv/bin/python run.py --split validation --no-read \
  --out preds/val_retrieval.jsonl

# Historical full-pipeline configuration; requires PDFs and hosted services.
.venv/bin/python run.py --split test --llm-select --visual-table \
  --max-papers 3 --mc-samples 1 --rpm 14 --out preds/test.jsonl

# Validate prediction structure against the downloaded inputs and metadata.
.venv/bin/python scripts/validate_submission.py \
  --input data/test.jsonl --pred preds/test.jsonl
```

These are documented entry points, **not newly verified reproduction commands**. The separately hosted dataset is distributed under **CC BY-NC 4.0**, and source PDFs/model weights may have separate terms. [`download_data.sh`](scripts/download_data.sh) fetches upstream `main` without a pinned revision; preserve hashes for exact replication. It does not replace the project's extended validator; `--organizers` downloads pristine organizer scripts separately. The [data guide](data/README.md) lists inputs. The requirements pin ordinary PyTorch `2.6.0`; historical CUDA runs used `2.6.0+cu124`. Cache embedding/reranker models before a long run to avoid first-use downloads interacting with question timeouts.

## What the experiments taught us

The local evaluator combines paper F1, evidence F1 and an answer composite; the [scorer analysis](reports/endgame.md) explains why metric-component weights should not be confused with per-question weights. The [experiment index](docs/EXPERIMENT_INDEX.md) links **22 numbered experiments and the ablation runner**; reports retain failures and retracted interpretations rather than hiding them.

| Investigation | Recorded finding | Evidence |
| --- | --- | --- |
| Paper retrieval | Selecting from retrieved candidates helped in a validation comparison; generating paper titles directly was not a replacement for retrieval. | [Selection analysis](reports/paper_selection.md) |
| Table understanding | Rendered table cells helped one validation metric, while row-key quality and hidden-test transfer remained separate problems. | [Table-stage analysis](reports/table_stage.md) |
| Evidence and scoring | Page offsets, object locators, exact row labels, and null-cell rules materially changed measured scores. | [Evidence measurements](reports/e4_e6_measurements.md) · [Scoring fixes](reports/scoring_and_fixes.md) |
| Failed hypotheses | A free-selector comparison was retracted after rate-limit errors contaminated the experiment; other heuristic changes were rejected. | [Corrected selector analysis](reports/free_selectors_and_evidence.md) · [Hypotheses ledger](HYPOTHESES.md) |

These are **the team's historical observations**, not newly reproduced measurements. Validation results should not automatically be interpreted as hidden-test gains; see [leaderboard gap](reports/leaderboard_gap.md).

## Repository map

| Directory | Start here |
| --- | --- |
| [`littraceqa/`](littraceqa/) | Retrieval, PDF processing, model clients, reasoning and answer building |
| [`docs/`](docs/) | [Architecture](docs/ARCHITECTURE.md), [reproducibility](docs/REPRODUCIBILITY.md), [experiment index](docs/EXPERIMENT_INDEX.md) |
| [`exp/`](exp/) | Historical experiments and ablations, indexed in [`exp/README.md`](exp/README.md) |
| [`reports/`](reports/) | Detailed findings, corrections and manuscript audits |
| [`results/`](results/) | Partial evaluator log, retained scores and arithmetic checks |
| [`paper/`](paper/) | [Paper PDF](paper/littraceqa_system.pdf), LaTeX and bibliography; its README contains archived pre-camera-ready notes |
| [`submission/`](submission/) | Historical submitted predictions, including the manually audited artifact |
| [`scripts/`](scripts/) · [`schema/`](schema/) | Data/evaluation utilities, modified validator and submission schema |

## Authorship, limitations and license

**Omar Saqr and Mostafa Gaafar** developed this entry as team OdeD. The best manually audited submission is not a measurement of generalizable unattended accuracy. Exact reproduction additionally depends on dataset revision, PDF access, external model versions, quotas, and evaluation conventions; see the [paper](paper/littraceqa_system.pdf) and [reproducibility guide](docs/REPRODUCIBILITY.md). Repository licensing is documented in [LICENSE](LICENSE); external datasets, papers and model weights retain their own terms.
