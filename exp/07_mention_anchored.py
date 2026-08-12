"""Mention-anchored paper selection: one paper per named artefact.

exp/04 ranked one candidate list and cut at n. exp/06 showed embedding expansion
cannot recover gold clusters. Both treat the question as a single query.

But LitTraceQA questions name their artefacts: "compare how many iterations
Stable Score Distillation reports ... and the rotation matrix in RomanTex's
formulation" is two papers, one per name. So resolve each *mention* to its own
best paper and return that set -- the set size falls out of the question instead
of being predicted, and each named artefact is guaranteed a slot.

Compared here against the exp/04 winner (top-n of a single fused list).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from evaluate import prf
from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.retrieval.acronym import AcronymIndex
from littraceqa.retrieval.dense import DenseRetriever
from littraceqa.retrieval.expand import predict_set_size
from littraceqa.retrieval.lexical import BM25Index, NicknameIndex, extract_nicknames
from littraceqa.retrieval.scope import extract_scope, scope_indices

pool = PaperPool.load()
bm25 = BM25Index(pool)
nicknames = NicknameIndex(pool)
acronyms = AcronymIndex(pool)
dense = DenseRetriever(pool)
dense.build(show_progress=False)

questions = load_questions(DATA_DIR / "validation_inputs.jsonl")
gold = load_gold()


def resolve_mention(mention: str, restrict: set[int] | None) -> tuple[str, float] | None:
    """Best single paper for one artefact name, with a confidence proxy.

    Signal precedence is precision-ordered: an exact title n-gram beats a title
    initialism, which beats an abstract mention, which beats BM25.
    """
    hits = nicknames.lookup(mention, restrict=restrict, limit=8)
    title_hits = [(p, s) for p, s in hits if s >= NicknameIndex.TITLE_SCORE]
    if title_hits:
        return title_hits[0][0].paper_id, 1.0 if len(title_hits) == 1 else 0.8

    acronym_hits = acronyms.lookup(mention, restrict=restrict, limit=8)
    if len(acronym_hits) == 1:
        return acronym_hits[0][0].paper_id, 0.75

    if hits:
        return hits[0][0].paper_id, 0.5

    if acronym_hits:
        return acronym_hits[0][0].paper_id, 0.45

    bm = bm25.search(mention, top_k=1, candidates=restrict)
    return (bm[0][0].paper_id, 0.3) if bm else None


def mention_anchored(question, max_papers: int = 6) -> list[str]:
    scope = extract_scope(question.question)
    restrict = scope_indices(pool, scope)
    resolved: dict[str, float] = {}
    for mention in extract_nicknames(question.question):
        result = resolve_mention(mention, restrict)
        if result is None:
            continue
        paper_id, confidence = result
        resolved[paper_id] = max(resolved.get(paper_id, 0.0), confidence)
    ordered = [pid for pid, _ in sorted(resolved.items(), key=lambda kv: -kv[1])]

    # Backfill from a question-level search when nothing resolved.
    if not ordered:
        ordered = [p.paper_id for p, _ in bm25.search(question.question, 1, restrict)]

    prediction = predict_set_size(question.question)
    if prediction.confident:
        target = prediction.size
        if len(ordered) < target:
            for paper, _ in dense.search(question.question, 20, restrict):
                if paper.paper_id not in ordered:
                    ordered.append(paper.paper_id)
                if len(ordered) >= target:
                    break
        return ordered[:target]
    return ordered[:max_papers]


def score(policy, label: str) -> None:
    f1s, per_family = [], {}
    sizes = Counter()
    for q in questions:
        record = gold[q.query_id]
        gold_ids = {p["paper_id"] for p in record["gold_papers"]}
        pred = set(policy(q))
        sizes[len(pred)] += 1
        _, _, f1 = prf(gold_ids, pred)
        f1s.append(f1)
        per_family.setdefault(record["task_family"], []).append(f1)
    print(f"{label:<40} {np.mean(f1s):>8.3f} "
          f"{np.mean(per_family.get('hidden_source_single_paper', [0])):>8.3f} "
          f"{np.mean(per_family.get('multi_paper', [0])):>8.3f}   sizes={dict(sorted(sizes.items()))}")


print(f"{'policy':<40} {'paper F1':>8} {'single':>8} {'multi':>8}")
print("-" * 96)
score(lambda q: mention_anchored(q, max_papers=1), "mention-anchored, cap 1")
score(lambda q: mention_anchored(q, max_papers=2), "mention-anchored, cap 2")
score(lambda q: mention_anchored(q, max_papers=3), "mention-anchored, cap 3")
score(lambda q: mention_anchored(q, max_papers=6), "mention-anchored, cap 6")

# Baseline from exp/04 for comparison.
from littraceqa.retrieval.hybrid import HybridRetriever

retriever = HybridRetriever(pool, bm25, nicknames, dense=dense)
cache = {q.query_id: [c.paper.paper_id for c in retriever.retrieve(q.question, top_k=10)]
         for q in questions}
score(lambda q: cache[q.query_id][:1], "exp/04 winner: fused list, n=1")

print("\nWhat the test split would receive (no gold to score against):")
test = load_questions(DATA_DIR / "test.jsonl")
sizes = Counter(len(mention_anchored(q, max_papers=6)) for q in test)
print(f"  predicted paper-set sizes: {dict(sorted(sizes.items()))}")
