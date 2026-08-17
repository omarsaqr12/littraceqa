"""E1 -- does identify-then-match beat ranking title+abstract?

Baseline to beat (current pipeline, cross-encoder rerank):
    validation paper F1                     0.4901
    hidden_source_single_paper (test-like)  0.846

Success:  family F1 >= 0.95 and overall >= 0.60.
Kill:     family F1 < 0.87 -> fall back to using the model as a reranker over the
          existing candidate list instead of as a generator.

Reports identify-only, identify-with-retrieval-fallback, and the retrieval
baseline over the same questions, so the fallback's contribution is visible.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from evaluate import prf
from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.pipeline import Pipeline, PipelineConfig
from littraceqa.reason.client import GeminiClient
from littraceqa.retrieval.dense import DenseRetriever
from littraceqa.retrieval.identify import PaperIdentifier

pool = PaperPool.load()
gold = load_gold()
questions = load_questions(DATA_DIR / "validation_inputs.jsonl")

client = GeminiClient(rpm=14, timeout_seconds=120)
dense = DenseRetriever(pool)
dense.build(show_progress=False)
pipeline = Pipeline(
    pool, config=PipelineConfig(use_reranker=True), client=None, dense=dense
)
identifier = PaperIdentifier(pool, client, nicknames=pipeline.nicknames)

rows: list[dict] = []
for index, question in enumerate(questions, start=1):
    record = gold[question.query_id]
    gold_ids = {p["paper_id"] for p in record["gold_papers"]}
    trace = pipeline.select_papers(question)
    retrieved = trace.paper_ids

    result = identifier.identify(question.question)
    matched = result.matched_ids

    # Fallback: keep identification when it produced anything, else retrieval.
    # Never emit nothing -- abstention scores the same zero as a wrong answer.
    combined = matched or retrieved

    rows.append({
        "query_id": question.query_id,
        "family": record["task_family"],
        "gold": gold_ids,
        "retrieved": set(retrieved),
        "identified": set(matched),
        "combined": set(combined),
        "n_returned": len(result.papers),
        "n_matched": len(matched),
        "n_expected": result.n_expected,
        "ok": result.ok,
    })
    if index % 10 == 0:
        print(f"  {index}/{len(questions)}  {client.usage}", flush=True)

print()


def score(key: str, subset=None) -> tuple[float, float, float]:
    chosen = [r for r in rows if subset is None or r["family"] == subset]
    scores = [prf(r["gold"], r[key]) for r in chosen]
    return (
        float(np.mean([s[0] for s in scores])),
        float(np.mean([s[1] for s in scores])),
        float(np.mean([s[2] for s in scores])),
    )


FAMILY = "hidden_source_single_paper"
print(f"{'config':<34} {'P':>7} {'R':>7} {'F1':>7}")
print("-" * 58)
for label, key in (("retrieval baseline", "retrieved"),
                   ("identify only", "identified"),
                   ("identify + retrieval fallback", "combined")):
    p, r, f = score(key)
    print(f"{label:<34} {p:>7.4f} {r:>7.4f} {f:>7.4f}")

print(f"\non {FAMILY} (n={sum(1 for r in rows if r['family'] == FAMILY)}) -- the test-like regime")
print(f"{'config':<34} {'P':>7} {'R':>7} {'F1':>7}")
print("-" * 58)
for label, key in (("retrieval baseline", "retrieved"),
                   ("identify only", "identified"),
                   ("identify + retrieval fallback", "combined")):
    p, r, f = score(key, FAMILY)
    print(f"{label:<34} {p:>7.4f} {r:>7.4f} {f:>7.4f}")

matched_any = sum(1 for r in rows if r["identified"])
returned_any = sum(1 for r in rows if r["n_returned"])
print(f"\nidentify returned a title on   {returned_any}/{len(rows)}")
print(f"at least one matched the pool  {matched_any}/{len(rows)}")
print(f"titles returned but unmatched  {sum(r['n_returned'] - r['n_matched'] for r in rows)}")

print("\nunmatched or wrong on the test-like family:")
shown = 0
for r in rows:
    if r["family"] != FAMILY or shown >= 12:
        continue
    if r["identified"] & r["gold"]:
        continue
    shown += 1
    print(f"  {r['query_id']}: returned={r['n_returned']} matched={sorted(r['identified'])} "
          f"gold={sorted(r['gold'])}")

family_f1 = score("combined", FAMILY)[2]
overall_f1 = score("combined")[2]
print("\n=== verdict ===")
if family_f1 >= 0.95 and overall_f1 >= 0.60:
    print(f"  PASS: family {family_f1:.4f} >= 0.95, overall {overall_f1:.4f} >= 0.60")
elif family_f1 < 0.87:
    print(f"  KILL: family {family_f1:.4f} < 0.87 -> switch to reranker-over-candidates")
else:
    print(f"  PARTIAL: family {family_f1:.4f} (baseline 0.846), overall {overall_f1:.4f} "
          f"(baseline 0.4901). Improvement but below target; tune matching.")
print("usage:", client.usage)
