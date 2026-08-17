"""E1-successor -- recognition instead of recall.

E1 asked the model to *produce* the paper's title and killed on family F1 0.846.
The mechanism was measured, not guessed: of 29 unmatched titles, **0 were even
80% similar to a gold title** and the median similarity was 56. flash-lite knows
the artefact names ("DetAny3D", "MAGBIG") and invents plausible titles around
them -- "DetAny3D: Towards General Category 3D Object Detection" for a paper
actually called "Detect Anything 3D in the Wild".

Recall is the wrong task. Recognition is easier and is what the kill criterion
prescribed: hand over the retrieved candidates and ask which ones the question is
about. The knowledge hypothesis is unchanged; only the interface is.

Baseline: validation paper F1 0.4901, test-like family 0.8462.
"""

from __future__ import annotations

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
from littraceqa.retrieval.verify import LLMPaperSelector

pool = PaperPool.load()
gold = load_gold()
questions = load_questions(DATA_DIR / "validation_inputs.jsonl")

client = GeminiClient(rpm=14, timeout_seconds=120)
dense = DenseRetriever(pool)
dense.build(show_progress=False)
pipeline = Pipeline(pool, config=PipelineConfig(use_reranker=True), client=None, dense=dense)
selector = LLMPaperSelector(pool, client, shortlist=20)

rows = []
for index, question in enumerate(questions, start=1):
    record = gold[question.query_id]
    trace = pipeline.select_papers(question)
    selection = selector.select(question.question, trace.candidates)
    rows.append({
        "family": record["task_family"],
        "gold": {p["paper_id"] for p in record["gold_papers"]},
        "retrieved": set(trace.paper_ids),
        "selected": set(selection.paper_ids),
        "in_shortlist": bool(
            {p["paper_id"] for p in record["gold_papers"]} & set(trace.candidates[:20])
        ),
        "ok": selection.ok,
    })
    if index % 10 == 0:
        print(f"  {index}/{len(questions)}  {client.usage}", flush=True)

FAMILY = "hidden_source_single_paper"


def score(key, subset=None):
    chosen = [r for r in rows if subset is None or r["family"] == subset]
    s = [prf(r["gold"], r[key]) for r in chosen]
    return (float(np.mean([x[0] for x in s])), float(np.mean([x[1] for x in s])),
            float(np.mean([x[2] for x in s])))


print(f"\n{'config':<30} {'P':>7} {'R':>7} {'F1':>7}")
print("-" * 54)
for label, key in (("retrieval baseline", "retrieved"), ("LLM selection", "selected")):
    p, r, f = score(key)
    print(f"{label:<30} {p:>7.4f} {r:>7.4f} {f:>7.4f}")

print(f"\non {FAMILY} (n={sum(1 for r in rows if r['family'] == FAMILY)})")
print(f"{'config':<30} {'P':>7} {'R':>7} {'F1':>7}")
print("-" * 54)
for label, key in (("retrieval baseline", "retrieved"), ("LLM selection", "selected")):
    p, r, f = score(key, FAMILY)
    print(f"{label:<30} {p:>7.4f} {r:>7.4f} {f:>7.4f}")

reachable = sum(1 for r in rows if r["in_shortlist"])
got = sum(1 for r in rows if r["selected"] & r["gold"])
print(f"\ngold present in the 20-candidate shortlist: {reachable}/{len(rows)}")
print(f"selection then picked a gold paper:        {got}/{len(rows)}")
print(f"  -> recognition accuracy where possible:  {got}/{reachable} = {got/max(reachable,1):.1%}")

family_f1 = score("selected", FAMILY)[2]
overall = score("selected")[2]
print("\n=== verdict ===")
if family_f1 >= 0.95 and overall >= 0.60:
    print(f"  PASS: family {family_f1:.4f}, overall {overall:.4f}")
elif family_f1 > 0.8462:
    print(f"  IMPROVEMENT: family {family_f1:.4f} > 0.8462 baseline, overall {overall:.4f} "
          f"vs 0.4901")
else:
    print(f"  KILL: family {family_f1:.4f} <= 0.8462 baseline -> selection adds nothing "
          f"over the cross-encoder")
print("usage:", client.usage)
