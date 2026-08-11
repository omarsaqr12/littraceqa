"""Measure paper-retrieval recall of the zero-cost lexical stack on validation.

This is the ceiling check: if candidate generation cannot surface the gold papers,
no amount of downstream reading fixes it. Everything here is local and free.
"""

from __future__ import annotations

import sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.retrieval.lexical import BM25Index, NicknameIndex, extract_nicknames

t0 = time.time()
pool = PaperPool.load()
print(f"pool: {len(pool)} papers ({time.time()-t0:.1f}s)")

t0 = time.time()
bm25 = BM25Index(pool)
print(f"bm25 index: {len(bm25.postings)} terms ({time.time()-t0:.1f}s)")
nick = NicknameIndex(pool)
print(f"nickname index built ({time.time()-t0:.1f}s)")

questions = load_questions(DATA_DIR / "validation_inputs.jsonl")
gold = load_gold()

KS = [1, 3, 5, 10, 20, 50, 100]
hit_bm25 = Counter()
hit_hybrid = Counter()
full_bm25 = Counter()
full_hybrid = Counter()
nick_stats = []
per_family = {}

for q in questions:
    g = gold[q.query_id]
    gold_ids = {p["paper_id"] for p in g["gold_papers"]}
    family = g["task_family"]

    bm_ranked = [p.paper_id for p, _ in bm25.search(q.question, top_k=200)]

    names = extract_nicknames(q.question)
    nick_ids: list[str] = []
    for name in names:
        for p, _ in nick.lookup(name)[:20]:
            if p.paper_id not in nick_ids:
                nick_ids.append(p.paper_id)
    nick_stats.append((q.query_id, names, len(nick_ids & gold_ids) if False else
                       len(set(nick_ids) & gold_ids), len(gold_ids)))

    hybrid = nick_ids + [pid for pid in bm_ranked if pid not in set(nick_ids)]

    for k in KS:
        hit_bm25[k] += len(gold_ids & set(bm_ranked[:k])) / len(gold_ids)
        hit_hybrid[k] += len(gold_ids & set(hybrid[:k])) / len(gold_ids)
        full_bm25[k] += gold_ids <= set(bm_ranked[:k])
        full_hybrid[k] += gold_ids <= set(hybrid[:k])
    per_family.setdefault(family, []).append(
        (len(gold_ids & set(hybrid[:50])) / len(gold_ids))
    )

n = len(questions)
print(f"\n{'k':>5} | {'BM25 recall':>12} {'BM25 all-found':>15} | {'HYBRID recall':>14} {'HYB all-found':>14}")
for k in KS:
    print(f"{k:>5} | {hit_bm25[k]/n:>12.1%} {full_bm25[k]/n:>15.1%} | "
          f"{hit_hybrid[k]/n:>14.1%} {full_hybrid[k]/n:>14.1%}")

print("\nrecall@50 (hybrid) by task_family:")
for fam, vals in per_family.items():
    print(f"  {fam:<32} {sum(vals)/len(vals):.1%}  (n={len(vals)})")

print("\nnickname-only hits (gold found by pure nickname lookup):")
tot_hit = sum(h for _, _, h, _ in nick_stats)
tot_gold = sum(gt for _, _, _, gt in nick_stats)
print(f"  {tot_hit}/{tot_gold} = {tot_hit/tot_gold:.1%} of all gold papers")

print("\nworst cases (recall@50 == 0):")
for q in questions:
    g = gold[q.query_id]
    gold_ids = {p["paper_id"] for p in g["gold_papers"]}
    bm_ranked = [p.paper_id for p, _ in bm25.search(q.question, top_k=50)]
    names = extract_nicknames(q.question)
    nick_ids = [p.paper_id for name in names for p, _ in nick.lookup(name)[:20]]
    if not (gold_ids & (set(bm_ranked) | set(nick_ids))):
        print(f"  {q.query_id} [{g['task_family']}] names={names}")
        print(f"     Q: {q.question[:150]}")
