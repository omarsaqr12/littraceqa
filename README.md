# LitTraceQA — OdeD at GroundLM 2026

A research-question answering system that retrieves relevant papers from a 27,487-paper corpus, locates evidence in PDFs, and produces multiple-choice answers or schema-constrained tables. Built by team **OdeD: Omar Saqr and Mostafa Gaafar, The American University in Cairo** for the GroundLM 2026 shared task.

**Start here:** [system paper (PDF)](paper/littraceqa_system.pdf) · [paper source](paper/littraceqa_system.tex) · [pipeline](littraceqa/pipeline.py) · [experiments](exp/) · [findings](reports/) · [scored submissions](results/official_scores.csv).

## What the scores actually mean

| Run | Reported official score | Interpretation |
| --- | ---: | --- |
| First submission | 0.4563 | Initial shared-task submission |
| Best fully automated run | **0.5519** | Automated pipeline, without per-question human auditing |
| Best submission | **0.7649** | Source-PDF auditing of individual questions **plus leaderboard-feedback attribution**; **not** autonomous model performance or an estimate of generalization |

These are historical, reported shared-task scores, not scores independently reproduced by this repository audit. The best-submission artifact is [`submission/littraceqa-test_OdeD.jsonl`](submission/littraceqa-test_OdeD.jsonl). The [system paper](paper/littraceqa_system.pdf) and [scoring analysis](reports/scoring_and_fixes.md) explain the human-audited improvements and their limitations. Do not compare the audited number directly with fully automated systems.

## How the system works

`run.py` loads the paper pool and questions → `littraceqa/retrieval/` creates lexical/dense candidates, reranks and optionally selects papers using an LLM → `littraceqa/pdf/` fetches and reads source papers → `littraceqa/reason/` generates grounded answers and evidence locations → `littraceqa/answer/` produces the required submission schema → `scripts/validate_submission.py` checks output. See [`littraceqa/pipeline.py`](littraceqa/pipeline.py) for orchestration and [`HYPOTHESES.md`](HYPOTHESES.md) for rejected approaches. Experiments are research history, not a promise that every historical configuration remains runnable unchanged.

The project emphasizes careful evaluation: reports document unsuccessful heuristics, scorer interpretation, and previously retracted claims. Particularly useful entry points are [paper selection](reports/paper_selection.md), [table evidence](reports/table_stage.md), [free selectors and evidence](reports/free_selectors_and_evidence.md), [scoring and fixes](reports/scoring_and_fixes.md), and [the leaderboard gap](reports/leaderboard_gap.md).

## Reproduce what you can

A Linux environment is recommended; a fresh-checkout end-to-end run has **not** been verified in this audit. Python dependencies include PyTorch and local sentence-transformer models; a full pipeline may also need network access, API credentials, downloaded PDFs, and substantial compute. Review costs and quotas before running a full split.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/download_data.sh
cp .env.example .env  # enter your own keys; never commit .env
```

The dataset is separately hosted and is not committed; check its CC BY-NC 4.0 terms before reuse. The downloaded inputs and `paper_metadata.jsonl` must exist under `data/`. If models are downloaded on first use, the per-question timeout may fire during initialization; pre-cache the required embedding/reranker models. `requirements.txt` pins plain `torch==2.6.0`, while the project reports using `2.6.0+cu124` for CUDA. Results may depend on model/API versions and quota conditions.

```bash
# Paper selection only; does not require a hosted LLM API key, but loads local models.
.venv/bin/python run.py --split validation --no-read --out preds/val_retrieval.jsonl

# Historical full-pipeline configuration: needs a configured hosted LLM and PDFs.
.venv/bin/python run.py --split test --llm-select --visual-table \
  --max-papers 3 --mc-samples 1 --rpm 14 --out preds/test.jsonl

# Check the output against the released input and metadata.
.venv/bin/python scripts/validate_submission.py --input data/test.jsonl \
  --pred preds/test.jsonl
```

These are **commands to attempt**, not audit-passed reproduction claims. Do not run the full split just to inspect this repository. Inspect [published score records](results/official_scores.csv) or run the lightweight score-consistency script after installing Python:

```bash
.venv/bin/python results/validate_table3.py
```

That script checks arithmetic consistency of *retained official score components* and writes `results/table3_validation.csv`/`.json`; it does **not** rerun the evaluator on model outputs, establish paper retrieval accuracy, or independently verify the leaderboard. Its own notes say the exported evaluator log is partial and some rows lack retained components. For exact audit scope, consult [`results/validate_table3.py`](results/validate_table3.py) and [`results/evaluator_log.csv`](results/evaluator_log.csv).

## Finding and interpreting the artifacts

| Location | Contents |
| --- | --- |
| [`paper/`](paper/) | Manuscript PDF, LaTeX source, bibliography, figure generator, submission records; [`paper/README.md`](paper/README.md) is explicitly archived pre-camera-ready guidance, **not** the current submission checklist. |
| [`reports/`](reports/) | Detailed measurement notes, negative results, paper and camera-ready audits. |
| [`exp/`](exp/) | Numbered experiment scripts plus ablation runner; historical experiments may require private keys or uncached models. |
| [`results/`](results/) | Exported evaluator records, reported scores, arithmetic cross-check scripts and outputs. |
| [`scripts/`](scripts/) | Dataset downloader, evaluator and an extended submission validator (not an untouched upstream copy). |
| [`submission/`](submission/) | Historical submission artifacts; avoid overwriting. |
| [`schema/`](schema/) | Submission schema resources. |

The scoring decomposition implemented in the evaluation scripts is `answer = (multiple_choice_accuracy + table_row_f1_macro + table_cell_accuracy_macro) / 3` and `overall = (paper_f1_macro + evidence_f1_macro + answer) / 3`. See [`scripts/evaluate.py`](scripts/evaluate.py) and [`reports/endgame.md`](reports/endgame.md) for detailed qualifications; do not infer that all question types carry equal weight.

## Limitations and authorship

A leaderboard-assisted, manually audited submission does not demonstrate generalizable automatic question answering. Dataset and PDF availability, external API behavior, rate limits, model downloads, and evaluation conventions affect reproducibility. The [paper](paper/littraceqa_system.pdf) discusses these limitations. Both authors contributed to this team project; individual contributions should not be inferred from repository ownership alone. See [LICENSE](LICENSE) for the repository license; the dataset has separate terms.
