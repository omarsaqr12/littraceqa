"""Which free selector is best? Paper selection is the binding constraint.

Baseline: hosted gemini-flash-lite selector, validation paper F1 0.5837.
All arms reuse the SAME candidate lists from the shipped run, so only the
selector model varies.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)
from evaluate import prf
from littraceqa.corpus import PaperPool, load_gold, load_questions, read_jsonl, DATA_DIR
from littraceqa.reason.local_client import LocalChatClient
from littraceqa.retrieval.verify import LLMPaperSelector

pool = PaperPool.load(); gold = load_gold()
qs = {q.query_id: q for q in load_questions(DATA_DIR / "validation_inputs.jsonl")}
tr = {r["query_id"]: r for r in read_jsonl("preds/val_p3_trace.jsonl")}
hosted = {r["query_id"]: {x["paper_id"] for x in r["gold_papers"]}
          for r in read_jsonl("preds/val_p3.jsonl")}
G, C = "https://api.groq.com/openai", "https://api.cerebras.ai"
ARMS = [
    ("cerebras gpt-oss-120b", C, "CEREBRAS_API_KEY", "gpt-oss-120b"),
    ("groq gpt-oss-120b",     G, "GROQ_API_KEY",     "openai/gpt-oss-120b"),
    ("cerebras zai-glm-4.7",  C, "CEREBRAS_API_KEY", "zai-glm-4.7"),
    ("groq qwen3.6-27b",      G, "GROQ_API_KEY",     "qwen/qwen3.6-27b"),
]
base = np.array([prf({x["paper_id"] for x in gold[q]["gold_papers"]}, hosted[q])[2]
                 for q in sorted(qs)])
print(f"{'selector':<24}{'paperF1':>9}{'delta':>9}{'95% CI':>20}{'s/q':>7}  errors")
print(f"{'gemini-flash-lite':<24}{base.mean():>9.4f}{'--':>9}{'--':>20}{'--':>7}")
rng = np.random.default_rng(0)
for name, url, key, model in ARMS:
    client = LocalChatClient(url, api_key=os.environ.get(key), model=model, timeout=120)
    sel = LLMPaperSelector(pool, client, shortlist=20)
    f, start = [], time.time()
    for qid in sorted(qs):
        picked = sel.select(qs[qid].question, tr.get(qid, {}).get("candidates", []))
        f.append(prf({x["paper_id"] for x in gold[qid]["gold_papers"]}, set(picked.paper_ids))[2])
    f = np.array(f); d = f - base
    lo, hi = np.percentile([rng.choice(d, len(d), replace=True).mean() for _ in range(4000)], [2.5, 97.5])
    print(f"{name:<24}{f.mean():>9.4f}{d.mean():>+9.4f}   [{lo:+.4f},{hi:+.4f}]"
          f"{(time.time()-start)/len(f):>7.1f}  {client.usage.errors}")
