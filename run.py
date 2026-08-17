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
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv

from littraceqa.answer.build import deterministic_label, validate_records
from littraceqa.corpus import DATA_DIR, PaperPool, load_questions, read_jsonl, write_jsonl
from littraceqa.pdf.fetch import PDFFetcher
from littraceqa.pipeline import Pipeline, PipelineConfig
from littraceqa.reason.client import GeminiClient

SPLITS = {
    "validation": "validation_inputs.jsonl",
    "test": "test.jsonl",
    "test_extra": "test_extra.jsonl",
}


@contextmanager
def question_deadline(seconds: float, query_id: str):
    """Abandon a question after `seconds`, whatever it is blocked on.

    Uses SIGALRM rather than a thread because the observed hangs are inside
    blocking C-level socket reads, which a `concurrent.futures` timeout cannot
    interrupt -- it would leak the thread and still stall the run.
    """
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _fire(signum, frame):
        raise TimeoutError(f"{query_id}: exceeded {seconds:.0f}s budget")

    previous = signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="validation", choices=sorted(SPLITS))
    parser.add_argument("--out", default=None, help="Output JSONL (default preds/<split>.jsonl)")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N questions")
    parser.add_argument("--no-read", action="store_true",
                        help="Skip PDF reading and answering; paper selection only")
    # Opt-in. This was previously `--no-expansion` with
    # `use_expansion=not args.no_expansion`, which turned expansion ON by
    # default against PipelineConfig.use_expansion=False. Measured: the flag was
    # inert either way, because `select_papers` seeds the list to exactly `size`
    # members and `ClusterExpander.expand` then returns immediately -- toggling
    # it produces byte-identical predictions. Fixed because the contradiction
    # would bite the moment the seeding changed, not because it cost points.
    parser.add_argument("--expansion", action="store_true",
                        help="Cluster-expand the paper set (off by default; "
                             "measured inert under the current seeding)")
    parser.add_argument("--llm-select", action="store_true",
                        help="LLM picks the paper set from the reranked shortlist "
                             "(exp/13: validation paper F1 0.4901 -> 0.5837, "
                             "precision 0.614 -> 0.758). One call per question.")
    parser.add_argument("--no-rerank", action="store_true",
                        help="Disable cross-encoder reranking of candidates "
                             "(exp/08: paper F1 0.410 -> 0.490, single-paper "
                             "0.692 -> 0.846). On by default.")
    parser.add_argument("--selection", default="fused",
                        choices=["fused", "mention_anchored"],
                        help="fused = top-n of the RRF list (best on validation's "
                             "cluster regime); mention_anchored = one paper per "
                             "named artefact (targets the test regime)")
    parser.add_argument("--model", default=None, action="append", dest="models",
                        help="Model to use; repeat to set the rotation chain. "
                             "Free-tier quota is per model per day, so the "
                             "default chain is what makes a full run possible.")
    parser.add_argument("--reader", default="gemini", choices=["gemini", "local"],
                        help="gemini = hosted, quota-bound; local = a GPU model "
                             "with no quota (littraceqa/reason/local_llm.py)")
    parser.add_argument("--local-model", default=None,
                        help="Model id for --reader local")
    parser.add_argument("--local-base-url", default=None,
                        help="OpenAI-compatible endpoint for --reader local "
                             "(e.g. http://127.0.0.1:8080 for llama-server). "
                             "Required to use a GGUF model.")
    parser.add_argument("--local-ctx", type=int, default=None,
                        help="Context window of the served model, so the prompt "
                             "is sized to fit instead of being front-truncated")
    parser.add_argument("--local-samples", type=int, default=1,
                        help="Self-consistency samples for the local reader; "
                             "free, unlike the hosted path")
    parser.add_argument("--rpm", type=int, default=8, help="Client-side requests/minute cap")
    parser.add_argument("--max-papers", type=int, default=3,
                        help="PDFs read per question (API budget)")
    parser.add_argument("--mc-samples", type=int, default=3,
                        help="Self-consistency samples for multiple choice")
    parser.add_argument("--trace", default=None, help="Write per-question traces here")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ignore any existing .partial.jsonl and start fresh")
    parser.add_argument("--timeout", type=float, default=240.0,
                        help="Per-request API timeout in seconds")
    parser.add_argument("--question-timeout", type=float, default=420.0,
                        help="Hard per-question budget in seconds; 0 disables")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    questions = load_questions(DATA_DIR / SPLITS[args.split])
    if args.limit:
        questions = questions[: args.limit]

    print(f"loading pool ...", flush=True)
    pool = PaperPool.load()

    client = None
    reader = None
    if not args.no_read and args.reader == "local":
        from littraceqa.reason.local_llm import DEFAULT_MODEL, LocalReader

        reader = LocalReader(args.local_model or DEFAULT_MODEL,
                             samples=args.local_samples,
                             base_url=args.local_base_url,
                             context_tokens=args.local_ctx)
        print(f"loading local reader {reader.model_name} ...", flush=True)
        reader.load()  # eagerly, outside the per-question watchdog
        # Still build a client when a key exists: the table solver needs one,
        # and it costs nothing until it is called.
        client = GeminiClient(model=args.models, rpm=args.rpm,
                              timeout_seconds=args.timeout)
        client = client if client.available else None

    if not args.no_read and args.reader == "gemini":
        client = GeminiClient(model=args.models, rpm=args.rpm,
                              timeout_seconds=args.timeout)
        if not client.available:
            print("ERROR: GEMINI_API_KEY is not set.\n"
                  "  Get a free key at https://aistudio.google.com/apikey, put it in .env,\n"
                  "  or run with --no-read for local-only paper selection.", file=sys.stderr)
            return 2

    config = PipelineConfig(
        selection=args.selection,
        use_reranker=not args.no_rerank,
        use_llm_selector=args.llm_select,
        use_expansion=args.expansion,
        max_papers_to_read=args.max_papers,
        mc_samples=args.mc_samples,
    )
    print("building indices ...", flush=True)
    pipeline = Pipeline(pool, config=config, client=client, fetcher=PDFFetcher(),
                        reader=reader)

    out_path = Path(args.out or f"preds/{args.split}.jsonl")
    partial_path = out_path.with_suffix(".partial.jsonl")

    # Resume: a power cut and a hung API call have each already cost a full run,
    # so completed questions are appended to disk as they finish and reloaded on
    # restart. The LLM disk cache makes re-running cheap, but not free.
    done: dict[str, dict] = {}
    if partial_path.exists() and not args.no_resume:
        for row in read_jsonl(partial_path):
            if isinstance(row, dict) and row.get("query_id"):
                done[row["query_id"]] = row
        print(f"resuming: {len(done)} questions already done in {partial_path}")

    records, traces = [], []
    started = time.time()
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    partial = partial_path.open("a", encoding="utf-8")
    for index, question in enumerate(questions, start=1):
        if question.query_id in done:
            records.append(done[question.query_id])
            continue
        try:
            # Hard watchdog. Library-level timeouts have repeatedly failed to
            # bound a call -- the SDK's http_options timeout does not cover
            # every path, and a run was observed frozen with zero CPU on an
            # ESTABLISHED connection. SIGALRM interrupts the blocking syscall
            # itself, so a question can always be abandoned and the run
            # continues. The partial file keeps whatever completed.
            with question_deadline(args.question_timeout, question.query_id):
                record, trace = pipeline.run_question(question)
        except Exception as exc:  # keep going: a partial file still scores
            print(f"  [{question.query_id}] FAILED: {exc}", file=sys.stderr)
            from littraceqa.answer.build import build_record

            # Never emit an empty paper set just because the reader died. Stages
            # A-C are local, free and deterministic, so re-running them costs
            # about a second and recovers the 36.4% of the score that paper F1
            # carries. Only if retrieval itself is broken do we give up.
            try:
                with question_deadline(args.question_timeout, question.query_id):
                    paper_ids = pipeline.select_papers(question).paper_ids
            except Exception as retrieval_exc:  # noqa: BLE001
                print(f"  [{question.query_id}] retrieval also failed: {retrieval_exc}",
                      file=sys.stderr)
                paper_ids = []
            record = build_record(question, paper_ids, [], {})
            trace = None
        records.append(record)
        partial.write(json.dumps(record, ensure_ascii=False) + "\n")
        partial.flush()
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

    partial.close()
    write_jsonl(records, out_path)
    print(f"\nwrote {len(records)} records -> {out_path}")

    if args.trace:
        write_jsonl(traces, Path(args.trace))
        print(f"wrote traces -> {args.trace}")

    # Health check. Both of these are silent failures: a record with no evidence
    # still validates and still scores, it just scores zero, and a fallback MC
    # label is indistinguishable from a real one in the output file. Counting
    # them is the only way a bad run announces itself before the leaderboard does.
    by_id = {q.query_id: q for q in questions}
    empty_evidence = [r["query_id"] for r in records if not r.get("evidence")]
    fallbacks = []
    for record in records:
        question = by_id.get(record.get("query_id"))
        if question is None or "multiple_choice" not in question.answer_types:
            continue
        options = sorted(question.multiple_choice_options or {})
        emitted = str((record.get("answer", {}).get("multiple_choice") or {}).get("gold") or "")
        if options and emitted == deterministic_label(record["query_id"], options):
            fallbacks.append(record["query_id"])

    mc_total = sum(1 for q in questions if "multiple_choice" in q.answer_types)
    print(f"\nempty evidence: {len(empty_evidence)}/{len(records)}")
    if empty_evidence:
        print(f"  {', '.join(empty_evidence[:12])}"
              + (" ..." if len(empty_evidence) > 12 else ""))
    print(f"suspected MC fallbacks: {len(fallbacks)}/{mc_total} "
          f"(upper bound -- a real answer can coincide with the seeded guess)")

    errors = validate_records(records, questions, {p.paper_id for p in pool.papers})
    if errors:
        print(f"\nVALIDATION FAILED: {len(errors)} error(s)")
        for error in errors[:20]:
            print(f"  - {error}")
        return 1
    print("validation: OK")

    gold_path = DATA_DIR / "validation.jsonl"
    if args.split == "validation" and gold_path.exists():
        # Aliased: a bare `read_jsonl` here would shadow the module-level import
        # for the whole function, breaking the resume path above.
        from evaluate import evaluate, read_jsonl as read_gold_jsonl

        gold = read_gold_jsonl(gold_path)
        if args.limit:
            keep = {q.query_id for q in questions}
            gold = [g for g in gold if g["query_id"] in keep]
        result = evaluate(gold, records)
        print("\nofficial metrics:")
        print(json.dumps(result["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
