#!/usr/bin/env python3
"""Run the LitTraceQA pipeline over a split and write a submission file.

    # paper selection only -- local, free, no API key needed
    python run.py --split validation --no-read --out preds/val_retrieval.jsonl

    # full pipeline
    python run.py --split test --out preds/test.jsonl

Always validates the output with the official validator before writing, and
scores it with the official evaluator when gold labels exist.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv

from littraceqa.answer.build import validate_records
from littraceqa.corpus import DATA_DIR, PaperPool, load_questions, write_jsonl
from littraceqa.pdf.fetch import PDFFetcher
from littraceqa.pipeline import Pipeline, PipelineConfig
from littraceqa.reason.client import GeminiClient

SPLITS = {
    "validation": "validation_inputs.jsonl",
    "test": "test.jsonl",
    "test_extra": "test_extra.jsonl",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="validation", choices=sorted(SPLITS))
    parser.add_argument("--out", default=None, help="Output JSONL (default preds/<split>.jsonl)")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N questions")
    parser.add_argument("--no-read", action="store_true",
                        help="Skip PDF reading and answering; paper selection only")
    parser.add_argument("--no-expansion", action="store_true")
    parser.add_argument("--selection", default="fused",
                        choices=["fused", "mention_anchored"],
                        help="fused = top-n of the RRF list (best on validation's "
                             "cluster regime); mention_anchored = one paper per "
                             "named artefact (targets the test regime)")
    parser.add_argument("--model", default=None, action="append", dest="models",
                        help="Model to use; repeat to set the rotation chain. "
                             "Free-tier quota is per model per day, so the "
                             "default chain is what makes a full run possible.")
    parser.add_argument("--rpm", type=int, default=8, help="Client-side requests/minute cap")
    parser.add_argument("--max-papers", type=int, default=3,
                        help="PDFs read per question (API budget)")
    parser.add_argument("--mc-samples", type=int, default=3,
                        help="Self-consistency samples for multiple choice")
    parser.add_argument("--trace", default=None, help="Write per-question traces here")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    questions = load_questions(DATA_DIR / SPLITS[args.split])
    if args.limit:
        questions = questions[: args.limit]

    print(f"loading pool ...", flush=True)
    pool = PaperPool.load()

    client = None
    if not args.no_read:
        client = GeminiClient(model=args.models, rpm=args.rpm)
        if not client.available:
            print("ERROR: GEMINI_API_KEY is not set.\n"
                  "  Get a free key at https://aistudio.google.com/apikey, put it in .env,\n"
                  "  or run with --no-read for local-only paper selection.", file=sys.stderr)
            return 2

    config = PipelineConfig(
        selection=args.selection,
        use_expansion=not args.no_expansion,
        max_papers_to_read=args.max_papers,
        mc_samples=args.mc_samples,
    )
    print("building indices ...", flush=True)
    pipeline = Pipeline(pool, config=config, client=client, fetcher=PDFFetcher())

    records, traces = [], []
    started = time.time()
    for index, question in enumerate(questions, start=1):
        try:
            record, trace = pipeline.run_question(question)
        except Exception as exc:  # keep going: a partial file still scores
            print(f"  [{question.query_id}] FAILED: {exc}", file=sys.stderr)
            from littraceqa.answer.build import build_record

            record = build_record(question, [], [], {})
            trace = None
        records.append(record)
        if trace is not None:
            traces.append({
                "query_id": trace.query_id,
                "mentions": trace.mentions,
                "predicted_size": trace.predicted_size,
                "size_reason": trace.size_reason,
                "paper_ids": trace.paper_ids,
                "candidates": trace.candidates[:10],
                "fetch_failures": trace.fetch_failures,
                "readings": [
                    {"paper_id": r.paper_id, "found": r.found, "answer": r.answer,
                     "confidence": r.confidence, "evidence": r.evidence, "error": r.error}
                    for r in trace.readings
                ],
            })
        if index % 5 == 0 or index == len(questions):
            rate = (time.time() - started) / index
            print(f"  {index}/{len(questions)}  {rate:.1f}s/question"
                  + (f"  {client.usage}" if client else ""), flush=True)

    out_path = Path(args.out or f"preds/{args.split}.jsonl")
    write_jsonl(records, out_path)
    print(f"\nwrote {len(records)} records -> {out_path}")

    if args.trace:
        write_jsonl(traces, Path(args.trace))
        print(f"wrote traces -> {args.trace}")

    errors = validate_records(records, questions, {p.paper_id for p in pool.papers})
    if errors:
        print(f"\nVALIDATION FAILED: {len(errors)} error(s)")
        for error in errors[:20]:
            print(f"  - {error}")
        return 1
    print("validation: OK")

    gold_path = DATA_DIR / "validation.jsonl"
    if args.split == "validation" and gold_path.exists():
        from evaluate import evaluate, read_jsonl

        gold = read_jsonl(gold_path)
        if args.limit:
            keep = {q.query_id for q in questions}
            gold = [g for g in gold if g["query_id"] in keep]
        result = evaluate(gold, records)
        print("\nofficial metrics:")
        print(json.dumps(result["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
