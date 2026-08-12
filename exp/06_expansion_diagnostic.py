"""Is cluster expansion viable, given a perfect seed?

The set-size sweep (exp/04) showed expansion never beats returning the single
top candidate. Two very different causes produce that result:

  (a) the seed is usually wrong, so expansion amplifies an error, or
  (b) the gold cluster is not a dense-embedding neighbourhood at all, so even a
      perfect seed cannot reach its siblings.

(a) is fixable with a better ranker. (b) means expansion is a dead end and the
effort belongs elsewhere. This distinguishes them by seeding with a *gold* paper
and measuring how much of the rest of the cluster kNN recovers.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.retrieval.dense import DenseRetriever
from littraceqa.textnorm import clean

pool = PaperPool.load()
dense = DenseRetriever(pool)
dense.build(show_progress=False)
gold = load_gold()
questions = load_questions(DATA_DIR / "validation_inputs.jsonl")

multi = [q for q in questions if gold[q.query_id]["task_family"] == "multi_paper"]
print(f"{len(multi)} multi_paper questions\n")

KS = [3, 5, 10, 20, 50, 200]
recovered = {k: [] for k in KS}
rank_of_siblings: list[int] = []

for q in multi:
    gold_ids = [p["paper_id"] for p in gold[q.query_id]["gold_papers"]]
    if len(gold_ids) < 2:
        continue
    seed, siblings = gold_ids[0], set(gold_ids[1:])
    neighbours = [p.paper_id for p, _ in dense.neighbours([seed], top_k=max(KS))]
    for k in KS:
        found = len(siblings & set(neighbours[:k]))
        recovered[k].append(found / len(siblings))
    for sibling in siblings:
        rank_of_siblings.append(
            neighbours.index(sibling) + 1 if sibling in neighbours else 10**6
        )

print("Seeded with a GOLD paper, how much of the rest of the cluster does kNN recover?")
print(f"{'k':>5} | {'sibling recall':>15}")
for k in KS:
    print(f"{k:>5} | {np.mean(recovered[k]):>15.1%}")

ranks = np.array(rank_of_siblings)
found = ranks < 10**6
print(f"\nsiblings reachable at all (top-200): {found.mean():.1%}")
if found.any():
    print(f"median rank when found: {int(np.median(ranks[found]))}")

print("\n--- a cluster, and what kNN actually returns for it ---")
example = next(q for q in multi if len(gold[q.query_id]["gold_papers"]) == 4)
gold_ids = [p["paper_id"] for p in gold[example.query_id]["gold_papers"]]
print(f"{example.query_id}: {example.question[:110]}")
print("GOLD:")
for pid in gold_ids:
    print(f"   {pid} {clean(pool[pid].title)[:72]}")
print(f"kNN from {gold_ids[0]}:")
for paper, score in dense.neighbours([gold_ids[0]], top_k=8):
    mark = "  <-- GOLD" if paper.paper_id in gold_ids else ""
    print(f"   {score:.3f} {paper.paper_id} {clean(paper.title)[:64]}{mark}")
