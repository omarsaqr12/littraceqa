"""Where does the gold paper sit in the ranked candidate list?

Two independent selectors agree on 71/71 test questions and both leave a 0.20
paper-F1 gap, so the gap is not selection quality -- the gold paper is not in the
shortlist for the selector to find. This measures the recall curve directly, split
by task family, because only the named-paper family resembles the test split.

If gold clusters at ranks 21-40, widening `llm_shortlist` is a real fix. If gold
is either at rank 1 or absent entirely, shortlist width is irrelevant and the
ceiling is retrieval itself.

Free: no API calls, `use_llm_selector=False`.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.pipeline import Pipeline, PipelineConfig

DEEP_K = 200


def main() -> None:
    pool = PaperPool.load()
    gold = load_gold()
    questions = load_questions(DATA_DIR / "validation_inputs.jsonl")

    cfg = PipelineConfig(
        candidate_k=DEEP_K, use_llm_selector=False, use_reranker=True,
        use_dense=True, use_acronyms=True, use_expansion=False,
    )
    pipeline = Pipeline(pool, config=cfg)

    ranks: dict[str, list[int | None]] = collections.defaultdict(list)
    for question in questions:
        record = gold[question.query_id]
        family = record["task_family"]
        candidates = pipeline.select_papers(question).candidates
        position = {pid: i for i, pid in enumerate(candidates)}
        for paper in record["gold_papers"]:
            ranks[family].append(position.get(paper["paper_id"]))

    cuts = [1, 5, 10, 20, 30, 40, 60, 100, DEEP_K]
    print(f"gold-paper rank in the candidate list (candidate_k={DEEP_K})\n")
    for family, values in ranks.items():
        total = len(values)
        print(f"{family}  (n={total} gold papers)")
        for cut in cuts:
            hit = sum(1 for r in values if r is not None and r < cut)
            print(f"    recall@{cut:<4} {hit/total:.3f}  ({hit}/{total})")
        missing = sum(1 for r in values if r is None)
        print(f"    unreachable at {DEEP_K}: {missing}/{total}\n")

    named = [r for r in ranks.get("hidden_source_single_paper", []) if r is not None]
    band = sum(1 for r in named if 20 <= r < 40)
    print("VERDICT (named-paper family, the test-like one):")
    print(f"  gold in ranks 21-40, i.e. gained by widening shortlist 20 -> 40: {band}")
    print(f"  gold at rank 1 already: {sum(1 for r in named if r == 0)}")


if __name__ == "__main__":
    main()
