"""H7 -- drop selected papers whose full text never mentions the question's artefacts.

Baseline (v10 config, validation): paper P 0.7582 R 0.5364 F1 0.5837.
Success: precision >= 0.95 with recall down no more than 0.02.
Kill:    precision gain < 0.05.

Local only: cached PDFs, no API calls. Reuses the paper sets already chosen by
the shipped pipeline, so this isolates the filter and nothing else.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
from evaluate import prf
from littraceqa.corpus import PaperPool, load_gold, load_questions, read_jsonl, DATA_DIR
from littraceqa.pdf.fetch import PDFFetcher
from littraceqa.retrieval.lexical import extract_nicknames
from littraceqa.retrieval.mention_verify import MentionVerifier

pool = PaperPool.load(); gold = load_gold()
qs = {q.query_id: q for q in load_questions(DATA_DIR / "validation_inputs.jsonl")}
trace = {r["query_id"]: r for r in read_jsonl("preds/val_p3.jsonl")}
verifier = MentionVerifier(pool, PDFFetcher())

before = []; after = []; dropped = 0; dropped_gold = 0
for qid, g in gold.items():
    goldset = {p["paper_id"] for p in g["gold_papers"]}
    chosen = [p["paper_id"] for p in trace[qid]["gold_papers"]]
    if not chosen:
        continue
    mentions = extract_nicknames(qs[qid].question)
    kept, scored = verifier.filter(chosen, mentions)
    before.append(prf(goldset, set(chosen)))
    after.append(prf(goldset, set(kept)))
    removed = set(chosen) - set(kept)
    dropped += len(removed)
    dropped_gold += len(removed & goldset)
    if removed:
        print(f"  {qid}: dropped {sorted(removed)}"
              + ("  <-- WAS GOLD" if removed & goldset else ""))

def agg(rows, i): return float(np.mean([r[i] for r in rows]))
print(f"\n{'':<10}{'P':>8}{'R':>8}{'F1':>8}")
print(f"{'before':<10}{agg(before,0):>8.4f}{agg(before,1):>8.4f}{agg(before,2):>8.4f}")
print(f"{'after':<10}{agg(after,0):>8.4f}{agg(after,1):>8.4f}{agg(after,2):>8.4f}")
print(f"\npapers dropped: {dropped} ({dropped_gold} of them gold)")
dp = agg(after,0)-agg(before,0); dr = agg(after,1)-agg(before,1)
print(f"precision {dp:+.4f}, recall {dr:+.4f}, F1 {agg(after,2)-agg(before,2):+.4f}")
print("\n=== verdict ===")
if agg(after,0) >= 0.95 and dr >= -0.02: print("  PASS")
elif dp < 0.05: print(f"  KILL: precision gain {dp:+.4f} < 0.05")
else: print(f"  PARTIAL: precision {dp:+.4f}, recall {dr:+.4f}")
