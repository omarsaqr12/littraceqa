"""Does cross-encoder reranking close the 0.40 -> 0.756 selection gap?

reports/retrieval_findings.md isolated selection as the bottleneck. This measures
the fix: rerank the same top-40 candidate list and re-run the selection policies
on top of it.

Reports precision@1 and paper F1 so the two failure modes stay separable --
picking the wrong single paper vs. picking the wrong number of papers.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from evaluate import prf
from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions
from littraceqa.pipeline import Pipeline, PipelineConfig
from littraceqa.retrieval.dense import DenseRetriever
from littraceqa.retrieval.expand import predict_set_size
from littraceqa.retrieval.rerank import CrossEncoderReranker

pool = PaperPool.load()
dense = DenseRetriever(pool)
dense.build(show_progress=False)
pipeline = Pipeline(pool, config=PipelineConfig(), client=None, dense=dense)

questions = load_questions(DATA_DIR / "validation_inputs.jsonl")
gold = load_gold()

print("generating candidates ...", flush=True)
traces = {q.query_id: pipeline.select_papers(q) for q in questions}

reranker = CrossEncoderReranker(pool)


def evaluate_policy(ordering: dict[str, list[str]], label: str) -> None:
    p_at_1, f1_fixed1, f1_pred, per_family = [], [], [], {}
    for q in questions:
        record = gold[q.query_id]
        gold_ids = {p["paper_id"] for p in record["gold_papers"]}
        ranked = ordering[q.query_id]
        p_at_1.append(1.0 if ranked[:1] and ranked[0] in gold_ids else 0.0)
        f1_fixed1.append(prf(gold_ids, set(ranked[:1]))[2])
        size = max(1, min(predict_set_size(q.question).size, 6))
        f1 = prf(gold_ids, set(ranked[:size]))[2]
        f1_pred.append(f1)
        per_family.setdefault(record["task_family"], []).append(f1)
    print(f"{label:<34} {np.mean(p_at_1):>7.3f} {np.mean(f1_fixed1):>9.3f} "
          f"{np.mean(f1_pred):>9.3f} "
          f"{np.mean(per_family.get('hidden_source_single_paper', [0])):>8.3f} "
          f"{np.mean(per_family.get('multi_paper', [0])):>8.3f}")


print(f"\n{'ordering':<34} {'P@1':>7} {'F1(n=1)':>9} {'F1(pred)':>9} {'single':>8} {'multi':>8}")
print("-" * 82)
evaluate_policy({qid: t.candidates for qid, t in traces.items()}, "baseline (RRF fusion)")

for mode in ("question", "per_mention"):
    for prior_weight in (0.0, 0.25, 0.5):
        reranker.prior_weight = prior_weight
        started = time.time()
        ordering = {
            q.query_id: [
                c.paper.paper_id
                for c in reranker.rerank(
                    q.question,
                    traces[q.query_id].candidates,
                    mentions=traces[q.query_id].mentions,
                    mode=mode,
                )
            ]
            for q in questions
        }
        evaluate_policy(ordering, f"rerank {mode}, prior={prior_weight:.2f}"
                                 f" ({(time.time()-started)/len(questions):.1f}s/q)")

# Ceiling, unchanged by reranking -- it depends only on candidate recall.
oracle = [
    prf({p["paper_id"] for p in gold[q.query_id]["gold_papers"]},
        {p["paper_id"] for p in gold[q.query_id]["gold_papers"]}
        & set(traces[q.query_id].candidates))[2]
    for q in questions
]
print("-" * 82)
print(f"{'ORACLE over same candidates':<34} {'':>7} {'':>9} {np.mean(oracle):>9.3f}")
