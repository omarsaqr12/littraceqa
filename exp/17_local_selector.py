"""Can the local 27B do paper selection, so the stage stops being quota-bound?

Selection is the binding constraint on the score and the hosted path cannot
support experimenting on it: gemini-3.7-flash exhausts its free daily quota in
~15 calls. The local model is free and unlimited, and selection is the stage it
should be best at -- 30 titles and abstracts, pick indices.

Baseline: hosted flash-lite selector, validation paper F1 0.5837.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
from evaluate import prf
from littraceqa.corpus import PaperPool, load_gold, load_questions, read_jsonl, DATA_DIR
from littraceqa.reason.local_client import LocalChatClient
from littraceqa.retrieval.verify import LLMPaperSelector

pool = PaperPool.load(); gold = load_gold()
qs = {q.query_id: q for q in load_questions(DATA_DIR / "validation_inputs.jsonl")}
tr = {r["query_id"]: r for r in read_jsonl("preds/val_p3_trace.jsonl")}
hosted = {r["query_id"]: {x["paper_id"] for x in r["gold_papers"]}
          for r in read_jsonl("preds/val_p3.jsonl")}

client = LocalChatClient(model="/home/mohab/models/Qwen3.6-27B-UD-Q4_K_XL.gguf")
selector = LLMPaperSelector(pool, client, shortlist=20)
print("server reachable:", client.available, flush=True)

fh, fl = [], []
start = time.time()
for i, (qid, q) in enumerate(qs.items(), 1):
    goldset = {x["paper_id"] for x in gold[qid]["gold_papers"]}
    picked = selector.select(q.question, tr.get(qid, {}).get("candidates", []))
    fl.append(prf(goldset, set(picked.paper_ids))[2])
    fh.append(prf(goldset, hosted[qid])[2])
    if i % 10 == 0:
        print(f"  {i}/55  {(time.time()-start)/i:.1f}s/q  {client.usage}", flush=True)

d = np.array(fl) - np.array(fh)
rng = np.random.default_rng(0)
lo, hi = np.percentile([rng.choice(d, len(d), replace=True).mean() for _ in range(5000)], [2.5, 97.5])
print(f"\nhosted flash-lite:   paper F1 {np.mean(fh):.4f}")
print(f"local Qwen3.6-27B:   paper F1 {np.mean(fl):.4f}")
print(f"delta {d.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  changed {(d!=0).sum()}/55")
print("usage:", client.usage)
