# Reproducibility and evidence guide

This guide distinguishes *inspecting an artifact*, *checking reported arithmetic*, *running a pipeline*, and *independently reproducing an official score*. These are different claims. No new official score or end-to-end reproduction was produced by the September 2026 portfolio audit.

## Start without an API key or a GPU

1. Read the [system paper](../paper/littraceqa_system.pdf) and its [LaTeX source](../paper/littraceqa_system.tex). The archival [paper/README.md](../paper/README.md) describes an earlier pre-camera-ready state; use the PDF and [submission fields](../paper/openreview_fields.md) for the later manuscript record.
2. Read [paper selection](../reports/paper_selection.md), [table evidence](../reports/table_stage.md), [scoring and fixes](../reports/scoring_and_fixes.md), and the [failed-hypotheses ledger](../HYPOTHESES.md). These are research records; an earlier report is not automatically the final conclusion.
3. Examine [`results/official_scores.csv`](../results/official_scores.csv) and [`results/evaluator_log.csv`](../results/evaluator_log.csv). The latter is a *partial retained export*, not a census of all submissions.
4. With Python 3 and no third-party packages, run `python3 results/validate_table3.py` from the repository root. It recomputes the overall metric **from retained component scores** and compares it with the displayed overall within documented rounding tolerances. It writes `results/table3_validation.csv` and `results/table3_validation.json`; run it on a disposable checkout if you do not want to modify tracked reports. Rows with missing components are explicitly not independently checkable.

The score arithmetic script does not evaluate prediction JSONL against private labels, independently establish that the official reported components are correct, or reproduce a model run. See its docstring and `scripts/evaluate.py` for the implemented formulas.

## Prepare a local pipeline run

From a fresh checkout in an environment with a supported Python version (exact historical OS/Python version was not fixed in this repository):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/download_data.sh
cp .env.example .env
```

Review the dataset's [CC BY-NC 4.0 release](https://huggingface.co/datasets/LitTraceQA/LitTraceQA) and other PDF licenses before downloading or redistributing content. The downloader pulls from upstream `main`, **without an immutable revision or checksum**; hash and pin downloaded inputs for a strict reproduction. The tracked validator is a project-modified copy. `bash scripts/download_data.sh --organizers` downloads pristine organizer evaluator/validator files under `scripts/organizers/` rather than overwriting project files. See [data/README.md](../data/README.md).

The requirements pin plain `torch==2.6.0`; historical GPU runs reported the CUDA 12.4 build `2.6.0+cu124`. Model weights for `bge-reranker-base` and `bge-large-en-v1.5` should be cached before a full run, because first-use downloads can interact badly with the per-question timeout. A GPU is optional for some local retrieval steps but not for all historical local-reader configurations. External PDF access and API quotas may block execution.

```bash
# Retrieval-only baseline: no hosted LLM key, but local model downloads may be required.
.venv/bin/python run.py --split validation --no-read \
  --out preds/val_retrieval.jsonl

# Historical full configuration: requires hosted services, network access and PDFs.
.venv/bin/python run.py --split test --llm-select --visual-table \
  --max-papers 3 --mc-samples 1 --rpm 14 --out preds/test.jsonl

# Validate the submission shape against the downloaded split and metadata.
.venv/bin/python scripts/validate_submission.py --input data/test.jsonl \
  --pred preds/test.jsonl
```

These commands are documented entry points, **not** fresh-checkout tests passed in the audit. A validated JSONL schema does not mean the answers are correct. The local development evaluator requires available gold labels: `python3 scripts/evaluate.py --help` lists its accepted options. The hidden-test official score cannot be independently recreated without organizer access to its gold labels and evaluator. Avoid spending API quota or downloading a large corpus merely to inspect this portfolio.

## Evidence levels

| Claim | Evidence currently in the repository | What it does *not* prove |
| --- | --- | --- |
| Best fully automated reported score: 0.5519 | Paper, reported scorer records and experiment notes | A newly rerun or independently validated automated performance number |
| Best submitted reported score: 0.7649 | [Historical submission JSONL](../submission/littraceqa-test_OdeD.jsonl), scorer records and paper | Autonomous performance; the team audited questions against PDFs and attributed leaderboard feedback |
| Scoring formula | [`scripts/evaluate.py`](../scripts/evaluate.py), [`results/validate_table3.py`](../results/validate_table3.py) | Agreement between locally computed predictions and hidden-test gold labels |
| Ablation effects | [Experiment scripts](../exp/), [reports](../reports/) | That all historical models, caches, external services and datasets can still be reconstructed |
| Manuscript typesetting | PDF, `.tex`, bibliography, figure script and [historical camera-ready audit](../reports/camera_ready_audit.md) | A fresh TeX build or an independent visual inspection performed by this portfolio audit |

## What to save with a new run

Record the Git commit; dataset revision and hashes; Python, PyTorch and CUDA versions; model names **and pinned revisions**; relevant CLI flags and random seeds; question split; API provider/model identifiers, usage or failure counters; original predictions; and any manual interventions. Keep keys in `.env` and out of commits and trace exports. Store raw predictions separately from edited submissions, and do not compare a manually audited score to a completely automated run as equivalent model results.

For code navigation, see [ARCHITECTURE.md](ARCHITECTURE.md). For individual experimental directions, see [EXPERIMENT_INDEX.md](EXPERIMENT_INDEX.md).
