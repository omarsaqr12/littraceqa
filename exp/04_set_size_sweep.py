"""How many papers should we return? Answer it by sweeping, not by heuristic.

`paper_f1_macro` trades precision against recall explicitly, so the optimal set
size is a decision-theoretic question, not a prediction problem. Gold set sizes
on validation are bimodal (26x1, 27x4), and §2.2 of plan.md shows the question
text barely distinguishes the two cases. This sweeps:

  * fixed n for n in 1..6
  * n from `predict_set_size` (surface cues only)
  * adaptive: expand while cosine-to-seed >= threshold

and reports macro paper F1 for each, overall and split by task family, so the
policy is chosen on measured expected value.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np

from evaluate import prf  # official implementation, not a reimplementation
from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.retrieval.acronym import AcronymIndex
from littraceqa.retrieval.dense import DenseRetriever
from littraceqa.retrieval.expand import ClusterExpander, predict_set_size
from littraceqa.retrieval.hybrid import HybridRetriever
from littraceqa.retrieval.lexical import BM25Index, NicknameIndex, extract_nicknames
from littraceqa.retrieval.scope import extract_scope

pool = PaperPool.load()
dense = DenseRetriever(pool)
dense.build(show_progress=True)
retriever = HybridRetriever(pool, BM25Index(pool), NicknameIndex(pool), dense=dense)
acronyms = AcronymIndex(pool)
expander = ClusterExpander(pool, dense)

questions = load_questions(DATA_DIR / "validation_inputs.jsonl")
gold = load_gold()

# Cache the ranked candidate list once; every policy reuses it.
ranked_by_qid: dict[str, list[str]] = {}
for q in questions:
    names = extract_nicknames(q.question)
    acronym_hits = [p.paper_id for name in names for p, _ in acronyms.lookup(name, limit=6)]
    cands = retriever.retrieve(q.question, top_k=40, extra_mentions=names)
    ranked = [c.paper.paper_id for c in cands]
    # Acronym hits are high precision but arrive unranked; interleave near the top.
    for pid in reversed(acronym_hits[:6]):
        if pid in ranked:
            ranked.remove(pid)
            ranked.insert(min(3, len(ranked)), pid)
    ranked_by_qid[q.query_id] = ranked


def score(policy) -> tuple[float, dict[str, float]]:
    per_family: dict[str, list[float]] = {}
    f1s = []
    for q in questions:
        g = gold[q.query_id]
        gold_ids = {p["paper_id"] for p in g["gold_papers"]}
        pred_ids = set(policy(q, ranked_by_qid[q.query_id]))
        _, _, f1 = prf(gold_ids, pred_ids)
        f1s.append(f1)
        per_family.setdefault(g["task_family"], []).append(f1)
    return float(np.mean(f1s)), {k: float(np.mean(v)) for k, v in per_family.items()}


print(f"\n{'policy':<42} {'paper F1':>9} {'single':>9} {'multi':>9}")
print("-" * 72)

for n in range(1, 7):
    total, fam = score(lambda q, ranked, n=n: ranked[:n])
    print(f"{'fixed n=' + str(n):<42} {total:>9.3f} "
          f"{fam.get('hidden_source_single_paper', 0):>9.3f} {fam.get('multi_paper', 0):>9.3f}")

total, fam = score(lambda q, ranked: ranked[: predict_set_size(q.question).size])
print(f"{'predict_set_size (surface cues)':<42} {total:>9.3f} "
      f"{fam.get('hidden_source_single_paper', 0):>9.3f} {fam.get('multi_paper', 0):>9.3f}")


def adaptive(q, ranked, threshold: float, cap: int = 6):
    if not ranked:
        return []
    seed = ranked[0]
    chosen = [seed]
    allowed = {pool.order[p] for p in ranked[1:20] if p in pool.order}
    for paper, sim in dense.neighbours([seed], top_k=cap * 3, candidates=allowed):
        if len(chosen) >= cap or sim < threshold:
            break
        chosen.append(paper.paper_id)
    return chosen


for threshold in (0.80, 0.83, 0.86, 0.89, 0.92, 0.95):
    total, fam = score(lambda q, r, t=threshold: adaptive(q, r, t))
    print(f"{'adaptive sim>=' + f'{threshold:.2f}':<42} {total:>9.3f} "
          f"{fam.get('hidden_source_single_paper', 0):>9.3f} {fam.get('multi_paper', 0):>9.3f}")


def hybrid_policy(q, ranked, threshold: float):
    """Trust an explicit count; otherwise let similarity decide how far to grow."""
    prediction = predict_set_size(q.question)
    if prediction.confident:
        return ranked[: prediction.size]
    return adaptive(q, ranked, threshold)


for threshold in (0.83, 0.86, 0.89, 0.92):
    total, fam = score(lambda q, r, t=threshold: hybrid_policy(q, r, t))
    print(f"{'count-if-confident else sim>=' + f'{threshold:.2f}':<42} {total:>9.3f} "
          f"{fam.get('hidden_source_single_paper', 0):>9.3f} {fam.get('multi_paper', 0):>9.3f}")

# Ceiling: how good could any policy be, given this candidate list?
oracle_size, oracle_any = [], []
for q in questions:
    g = gold[q.query_id]
    gold_ids = {p["paper_id"] for p in g["gold_papers"]}
    ranked = ranked_by_qid[q.query_id]
    oracle_size.append(max(prf(gold_ids, set(ranked[:n]))[2] for n in range(1, 11)))
    oracle_any.append(prf(gold_ids, gold_ids & set(ranked))[2])
print("-" * 72)
print(f"{'ORACLE: best fixed n per question':<42} {np.mean(oracle_size):>9.3f}")
print(f"{'ORACLE: all retrieved gold, no noise':<42} {np.mean(oracle_any):>9.3f}")
