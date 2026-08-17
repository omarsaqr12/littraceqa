"""Does gemini-3.7-flash select better once thinking is genuinely enabled?

The earlier attempt reported a score identical to six decimals with thinking off,
because thinking_budget was missing from the cache key -- the variable was never
tested. The key is fixed; 3.7-flash's per-day quota (~15 calls) rules out a full
55-question run, so this is a PAIRED comparison on a subset: the same questions,
the same candidate lists, flash-lite vs 3.7-flash.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)
from evaluate import prf
from littraceqa.corpus import PaperPool, load_gold, load_questions, read_jsonl, DATA_DIR
from littraceqa.reason.client import GeminiClient
from littraceqa.retrieval.verify import LLMPaperSelector

N = int(sys.argv[1]) if len(sys.argv) > 1 else 14
pool = PaperPool.load(); gold = load_gold()
qs = {q.query_id: q for q in load_questions(DATA_DIR / "validation_inputs.jsonl")}
tr = {r["query_id"]: r for r in read_jsonl("preds/val_p3_trace.jsonl")}
base = {r["query_id"]: {x["paper_id"] for x in r["gold_papers"]}
        for r in read_jsonl("preds/val_p3.jsonl")}

client = GeminiClient(rpm=6, timeout_seconds=300)
sel = LLMPaperSelector(pool, client, shortlist=20, model="gemini-3.7-flash")
print(f"selector thinking_budget={sel.thinking_budget} (-1 = model default, i.e. ON)")

ids = sorted(qs)[:N]
fa, fb, used = [], [], 0
for qid in ids:
    g = {x["paper_id"] for x in gold[qid]["gold_papers"]}
    try:
        picked = sel.select(qs[qid].question, tr.get(qid, {}).get("candidates", []))
    except Exception as exc:
        print(f"  {qid}: FAILED {str(exc)[:70]}"); break
    if client.usage.errors and client.usage.calls == used:
        print(f"  {qid}: no successful call -- quota likely gone"); break
    used = client.usage.calls
    fa.append(prf(g, base[qid])[2])
    fb.append(prf(g, set(picked.paper_ids))[2])
    print(f"  {qid}: flash-lite {fa[-1]:.2f}  3.7-flash {fb[-1]:.2f}  "
          f"n_picked={len(picked.paper_ids)}", flush=True)

if not fb:
    print("\nno usable comparisons -- quota exhausted before any call succeeded")
    raise SystemExit(0)
fa, fb = np.array(fa), np.array(fb)
d = fb - fa
print(f"\npaired on {len(d)} questions")
print(f"  flash-lite paper F1 {fa.mean():.4f}")
print(f"  3.7-flash  paper F1 {fb.mean():.4f}   delta {d.mean():+.4f}")
print(f"  changed {(d!=0).sum()}/{len(d)}   picked/q {np.mean([1]*len(fb)):.2f}")
print("usage:", client.usage)
