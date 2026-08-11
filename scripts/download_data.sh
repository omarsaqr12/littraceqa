#!/usr/bin/env bash
# Fetch the LitTraceQA release into data/ , scripts/ and schema/.
set -euo pipefail
BASE=https://huggingface.co/datasets/LitTraceQA/LitTraceQA/resolve/main
cd "$(dirname "$0")/.."
mkdir -p data schema scripts
for f in \
  data/paper_metadata.jsonl data/validation.jsonl data/validation_inputs.jsonl \
  data/sample_submission.jsonl data/test.jsonl data/test_sample_submission.jsonl \
  data/test_extra.jsonl data/test_extra_sample_submission.jsonl \
  scripts/evaluate.py scripts/validate_submission.py \
  schema/input.schema.json schema/submission.schema.json schema/littraceqa.schema.json
do
  echo "  $f"
  curl -sSL --fail -o "$f" "$BASE/$f"
done
echo "done: $(wc -l < data/paper_metadata.jsonl) papers"
