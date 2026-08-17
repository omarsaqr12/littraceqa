"""Why is candidate-generation recall stuck at 0.703?

Paper F1 is now bounded by whether gold is in the candidate list at all: at
top-20 the selector scored 0.5837 against a 0.5898 ceiling, so selection is
solved and generation is not.

This asks, for every gold paper the fused list misses, which individual signal
*could* have found it and at what rank. If a signal ranks it at 200 the fusion
is throwing it away; if no signal ranks it anywhere, the paper is unreachable by
lexical or dense means and needs a different mechanism.

Local only -- no API calls.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.retrieval.acronym import AcronymIndex
from littraceqa.retrieval.dense import DenseRetriever
from littraceqa.retrieval.hybrid import HybridRetriever
from littraceqa.retrieval.lexical import BM25Index, NicknameIndex, extract_nicknames
from littraceqa.retrieval.scope import extract_scope, scope_indices

pool = PaperPool.load()
gold = load_gold()
questions = load_questions(DATA_DIR / "validation_inputs.jsonl")

bm25 = BM25Index(pool)
nicknames = NicknameIndex(pool)
acronyms = AcronymIndex(pool)
dense = DenseRetriever(pool)
dense.build(show_progress=False)
fused = HybridRetriever(pool, bm25, nicknames, dense=dense)

DEPTH = 30
reachable = collections.Counter()
missing_rows = []
per_signal_rank: dict[str, list[int]] = collections.defaultdict(list)

for question in questions:
    record = gold[question.query_id]
    gold_ids = {p["paper_id"] for p in record["gold_papers"]}
    mentions = extract_nicknames(question.question)
    scope = extract_scope(question.question)

    shortlist = [
        c.paper.paper_id
        for c in fused.retrieve(question.question, top_k=DEPTH, extra_mentions=mentions)
    ]
    missed = gold_ids - set(shortlist)
    if not missed:
        continue

    # Where could each miss have come from, searching much deeper than we use?
    deep_bm25 = [p.paper_id for p, _ in bm25.search(question.question, 500)]
    deep_dense = [p.paper_id for p, _ in dense.search(question.question, 500)]
    nick_hits: list[str] = []
    acro_hits: list[str] = []
    for mention in mentions:
        nick_hits += [p.paper_id for p, _ in nicknames.lookup(mention, limit=60)]
        acro_hits += [p.paper_id for p, _ in acronyms.lookup(mention, limit=60)]

    for paper_id in missed:
        where = {}
        for name, ranked in (("bm25", deep_bm25), ("dense", deep_dense),
                             ("nickname", nick_hits), ("acronym", acro_hits)):
            if paper_id in ranked:
                where[name] = ranked.index(paper_id) + 1
                per_signal_rank[name].append(where[name])
        reachable["unreachable by any signal" if not where else "reachable, fusion lost it"] += 1
        missing_rows.append((question.query_id, record["task_family"], paper_id, where,
                             len(gold_ids), question.question[:70]))

total_gold = sum(len(gold[q.query_id]["gold_papers"]) for q in questions)
print(f"gold papers total: {total_gold}")
print(f"missed at top-{DEPTH}: {len(missing_rows)} ({len(missing_rows)/total_gold:.1%})\n")

print("=== can any single signal reach the miss, searching to depth 500? ===")
for key, count in reachable.most_common():
    print(f"  {count:>3}  {key}")

print("\n=== rank of the miss within each signal, when found ===")
for name, ranks in sorted(per_signal_rank.items(), key=lambda kv: -len(kv[1])):
    ranks = sorted(ranks)
    within30 = sum(1 for r in ranks if r <= 30)
    print(f"  {name:<9} found {len(ranks):>3}  median rank {int(np.median(ranks)):>4}  "
          f"within top-30: {within30}")

print("\n=== misses by task family ===")
for family, count in collections.Counter(r[1] for r in missing_rows).most_common():
    print(f"  {count:>3}  {family}")

print("\n=== sample misses ===")
for query_id, family, paper_id, where, n_gold, text in missing_rows[:14]:
    title = pool[paper_id].title[:52] if paper_id in pool.by_id else "?"
    print(f"  {query_id} [{family[:12]}] n_gold={n_gold} {paper_id}")
    print(f"     {title}")
    print(f"     reachable at: {where if where else 'NOWHERE in top-500 of any signal'}")
