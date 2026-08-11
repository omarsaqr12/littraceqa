"""Recall of the hybrid retriever vs. the BM25-only baseline, on validation."""

from __future__ import annotations

import sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.retrieval.hybrid import HybridRetriever
from littraceqa.retrieval.lexical import BM25Index, NicknameIndex, extract_nicknames
from littraceqa.retrieval.scope import extract_scope

pool = PaperPool.load()
bm25 = BM25Index(pool)
nick = NicknameIndex(pool)
retriever = HybridRetriever(pool, bm25, nick)

questions = load_questions(DATA_DIR / "validation_inputs.jsonl")
gold = load_gold()

KS = [1, 3, 5, 10, 20, 40]
recall = Counter()
allfound = Counter()
per_family: dict[str, list[float]] = {}
t0 = time.time()
misses = []

for q in questions:
    g = gold[q.query_id]
    gold_ids = {p["paper_id"] for p in g["gold_papers"]}
    cands = retriever.retrieve(q.question, top_k=40)
    ranked = [c.paper.paper_id for c in cands]
    for k in KS:
        recall[k] += len(gold_ids & set(ranked[:k])) / len(gold_ids)
        allfound[k] += gold_ids <= set(ranked[:k])
    per_family.setdefault(g["task_family"], []).append(
        len(gold_ids & set(ranked[:40])) / len(gold_ids)
    )
    if not (gold_ids & set(ranked[:40])):
        misses.append((q.query_id, g["task_family"], extract_nicknames(q.question), q.question))

n = len(questions)
print(f"hybrid retrieval over {n} validation questions ({time.time()-t0:.1f}s total, "
      f"{(time.time()-t0)/n:.2f}s/question)\n")
print(f"{'k':>4} | {'recall':>8} | {'all gold found':>14}")
for k in KS:
    print(f"{k:>4} | {recall[k]/n:>8.1%} | {allfound[k]/n:>14.1%}")

print("\nrecall@40 by task_family:")
for fam, vals in sorted(per_family.items()):
    print(f"  {fam:<32} {sum(vals)/len(vals):>6.1%}  (n={len(vals)})")

print(f"\ncomplete misses ({len(misses)}):")
for qid, fam, names, question in misses:
    print(f"  {qid} [{fam}] names={names}")
    print(f"     {question[:160]}")

print("\nscope extraction coverage:")
scoped = sum(1 for q in questions if not extract_scope(q.question).is_empty)
print(f"  {scoped}/{n} validation questions carry a venue/year scope")
test_qs = load_questions(DATA_DIR / "test.jsonl")
scoped_t = sum(1 for q in test_qs if not extract_scope(q.question).is_empty)
print(f"  {scoped_t}/{len(test_qs)} test questions carry a venue/year scope")
