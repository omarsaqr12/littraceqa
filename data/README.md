# Dataset and input files

The LitTraceQA dataset is **not vendored** in this repository. Its source is the [LitTraceQA dataset on Hugging Face](https://huggingface.co/datasets/LitTraceQA/LitTraceQA); the dataset has separate **CC BY-NC 4.0** terms. Review those terms before downloading or redistributing data. The code license in the repository does not relicense the dataset.

From the repository root, run `bash scripts/download_data.sh` to fetch the files listed in that script into this directory: `paper_metadata.jsonl`, `validation.jsonl`, `validation_inputs.jsonl`, `sample_submission.jsonl`, `test.jsonl`, `test_sample_submission.jsonl`, `test_extra.jsonl`, and `test_extra_sample_submission.jsonl`. The release used in the project lists 27,487 papers, 55 validation questions and 71 test questions; these are historical corpus/split descriptions, not a fresh dataset integrity check.

**Important distinction:** the downloader does **not** replace the tracked `scripts/evaluate.py`, `scripts/validate_submission.py`, or files under `schema/`. The tracked validator includes a project-specific all-null-row guard. To fetch pristine organizer evaluator and validator copies separately, run `bash scripts/download_data.sh --organizers`; the copies go to `scripts/organizers/`. Never overwrite the tracked scripts with the downloaded copies without reviewing the differences.

The shell script downloads the current upstream `main` files without version or hash pinning. For a strict reproduction, archive the input file hashes, upstream dataset revision, model revisions and API configuration alongside the run. See [`../docs/REPRODUCIBILITY.md`](../docs/REPRODUCIBILITY.md) for verification levels and the no-key inspection path.
