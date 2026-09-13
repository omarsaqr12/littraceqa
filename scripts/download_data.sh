#!/usr/bin/env bash
# Fetch the LitTraceQA release into data/.
#
# scripts/ and schema/ ship with this repository and are deliberately NOT
# fetched here. scripts/validate_submission.py is the organisers' validator
# extended with our dead-run guard (all-null table rows); overwriting it with
# the upstream copy would silently remove that check. Pristine organiser copies
# can be fetched into scripts/organizers/ with --organizers.
set -euo pipefail
BASE=https://huggingface.co/datasets/LitTraceQA/LitTraceQA/resolve/main
cd "$(dirname "$0")/.."
mkdir -p data

for f in \
  data/paper_metadata.jsonl data/validation.jsonl data/validation_inputs.jsonl \
  data/sample_submission.jsonl data/test.jsonl data/test_sample_submission.jsonl \
  data/test_extra.jsonl data/test_extra_sample_submission.jsonl
do
  echo "  $f"
  curl -sSL --fail -o "$f" "$BASE/$f"
done

if [[ "${1:-}" == "--organizers" ]]; then
  mkdir -p scripts/organizers
  for f in evaluate.py validate_submission.py; do
    echo "  scripts/organizers/$f"
    curl -sSL --fail -o "scripts/organizers/$f" "$BASE/scripts/$f"
  done
  echo "note: pristine organiser scripts are in scripts/organizers/;"
  echo "      scripts/validate_submission.py keeps our dead-run guard."
fi

echo "done: $(wc -l < data/paper_metadata.jsonl) papers"
