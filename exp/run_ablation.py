#!/usr/bin/env python3
"""Ablation harness: score named configurations on validation with the official metrics.

    python exp/run_ablation.py --stage retrieval          # local, free, no API key
    python exp/run_ablation.py --stage full --configs base expansion_off

Retrieval configs score `paper_f1_macro` only, which needs no API budget and is
the metric everything else depends on. Full configs run the whole pipeline and
report every official metric plus the per-evidence-type breakdown.

Results are written to reports/<stage>.json so the numbers in the system paper
are reproducible by flag rather than by rerunning a hand-edited script.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from evaluate import coarse_evidence_key, evaluate, prf, read_jsonl
from littraceqa.answer.build import build_record
from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.pipeline import Pipeline, PipelineConfig

REPORTS = ROOT / "reports"

#: Each entry overrides PipelineConfig defaults. Add a row, get a column.
RETRIEVAL_CONFIGS: dict[str, dict] = {
    "lexical_only":      dict(use_dense=False, use_acronyms=False, use_expansion=False),
    "lexical_acronym":   dict(use_dense=False, use_acronyms=True,  use_expansion=False),
    "hybrid_no_expand":  dict(use_dense=True,  use_acronyms=True,  use_expansion=False),
    "hybrid_expand_080": dict(use_dense=True,  use_acronyms=True,  use_expansion=True,
                              expansion_similarity=0.80),
    "hybrid_expand_086": dict(use_dense=True,  use_acronyms=True,  use_expansion=True,
                              expansion_similarity=0.86),
    "hybrid_expand_092": dict(use_dense=True,  use_acronyms=True,  use_expansion=True,
                              expansion_similarity=0.92),
    "hybrid_expand_fix4": dict(use_dense=True, use_acronyms=True,  use_expansion=True,
                               expansion_similarity=0.0, default_set_size=4),
}

FULL_CONFIGS: dict[str, dict] = {
    "base":          dict(),
    "expansion_off": dict(use_expansion=False),
    "read_1_paper":  dict(max_papers_to_read=1),
    "mc_greedy":     dict(mc_samples=1),
    "evidence_open": dict(evidence_confidence_floor=0.0),
}


def bootstrap_ci(values: list[float], n: int = 2000, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile CI. 55 questions is a small sample -- report the interval."""
    if not values:
        return (0.0, 0.0)
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(0)
    means = array[rng.integers(0, len(array), size=(n, len(array)))].mean(axis=1)
    return (float(np.percentile(means, 100 * alpha / 2)),
            float(np.percentile(means, 100 * (1 - alpha / 2))))


def score_retrieval(pipeline: Pipeline, questions, gold) -> dict:
    f1s, per_family = [], {}
    for question in questions:
        trace = pipeline.select_papers(question)
        record = gold[question.query_id]
        gold_ids = {p["paper_id"] for p in record["gold_papers"]}
        _, _, f1 = prf(gold_ids, set(trace.paper_ids))
        f1s.append(f1)
        per_family.setdefault(record["task_family"], []).append(f1)
    low, high = bootstrap_ci(f1s)
    return {
        "paper_f1_macro": float(np.mean(f1s)),
        "ci95": [low, high],
        "by_family": {k: float(np.mean(v)) for k, v in per_family.items()},
        "n": len(f1s),
    }


def evidence_breakdown(gold_records: list[dict], pred_records: list[dict]) -> dict:
    """Evidence F1 split by gold `primary_evidence_type` -- names the weakest path."""
    preds = {r["query_id"]: r for r in pred_records}
    buckets: dict[str, list[float]] = {}
    for record in gold_records:
        gold_keys = {coarse_evidence_key(e) for e in record.get("evidence", [])}
        pred_keys = {
            coarse_evidence_key(e)
            for e in preds.get(record["query_id"], {}).get("evidence", [])
        }
        _, _, f1 = prf(gold_keys, pred_keys)
        buckets.setdefault(record.get("primary_evidence_type", "unknown"), []).append(f1)
    return {k: {"f1": float(np.mean(v)), "n": len(v)} for k, v in sorted(buckets.items())}


def score_full(pipeline: Pipeline, questions, gold_records) -> dict:
    records = []
    for question in questions:
        try:
            record, _ = pipeline.run_question(question)
        except Exception as exc:
            print(f"    [{question.query_id}] failed: {exc}", file=sys.stderr)
            record = build_record(question, [], [], {})
        records.append(record)
    result = evaluate(gold_records, records)
    result["metrics"]["evidence_by_type"] = evidence_breakdown(gold_records, records)
    return result["metrics"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=["retrieval", "full"], default="retrieval")
    parser.add_argument("--configs", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default="gemini-flash-latest")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    table = RETRIEVAL_CONFIGS if args.stage == "retrieval" else FULL_CONFIGS
    names = args.configs or list(table)
    unknown = [n for n in names if n not in table]
    if unknown:
        print(f"unknown config(s): {unknown}\navailable: {list(table)}", file=sys.stderr)
        return 2

    questions = load_questions(DATA_DIR / "validation_inputs.jsonl")
    if args.limit:
        questions = questions[: args.limit]
    gold = load_gold()
    gold_records = [gold[q.query_id] for q in questions]

    pool = PaperPool.load()
    client = None
    if args.stage == "full":
        from littraceqa.reason.client import GeminiClient

        client = GeminiClient(model=args.model)
        if not client.available:
            print("GEMINI_API_KEY not set -- --stage full needs it. "
                  "Use --stage retrieval for the local-only ablation.", file=sys.stderr)
            return 2

    # Build the embedding matrix once and share it across configs.
    from littraceqa.retrieval.dense import DenseRetriever

    dense = DenseRetriever(pool)
    dense.build(show_progress=True)

    results = {}
    for name in names:
        config = PipelineConfig(**table[name])
        print(f"\n=== {name} ===\n{ {k: v for k, v in asdict(config).items()} }", flush=True)
        started = time.time()
        pipeline = Pipeline(pool, config=config, client=client, dense=dense)
        metrics = (score_retrieval(pipeline, questions, gold) if args.stage == "retrieval"
                   else score_full(pipeline, questions, gold_records))
        metrics["seconds"] = round(time.time() - started, 1)
        results[name] = {"config": asdict(config), "metrics": metrics}
        print(json.dumps(metrics, indent=2))

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{args.stage}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n{'config':<22} {'paper F1':>10}  {'95% CI':>16}  {'single':>8} {'multi':>8}"
          if args.stage == "retrieval" else f"\n{'config':<22} results")
    print("-" * 74)
    for name, entry in results.items():
        m = entry["metrics"]
        if args.stage == "retrieval":
            ci = m["ci95"]
            print(f"{name:<22} {m['paper_f1_macro']:>10.3f}  [{ci[0]:.3f}, {ci[1]:.3f}]  "
                  f"{m['by_family'].get('hidden_source_single_paper', 0):>8.3f} "
                  f"{m['by_family'].get('multi_paper', 0):>8.3f}")
        else:
            print(f"{name:<22} paper={m.get('paper_f1_macro')} "
                  f"evidence={m.get('evidence_f1_macro')} mc={m.get('multiple_choice_accuracy')}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
