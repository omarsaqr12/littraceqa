"""E7 -- read the table off the page instead of out of a text digest.

Baseline (control run, this session): row F1 0.5280, cell acc 0.2098.
Success: row F1 >= 0.65 and cell acc >= 0.45.  Kill: cell acc < 0.20.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)
from evaluate import prf, normalize_text, cell_equal
from littraceqa.answer.build import _conform_row
from littraceqa.answer.table_visual import VisualTableSolver
from littraceqa.corpus import DATA_DIR, PaperPool, load_gold, load_questions, read_jsonl
from littraceqa.pdf.fetch import PDFFetcher
from littraceqa.reason.client import GeminiClient
from littraceqa.reason.localize import Reading

pool = PaperPool.load(); gold = load_gold()
qs = {q.query_id: q for q in load_questions(DATA_DIR / "validation_inputs.jsonl")}
traces = {r["query_id"]: r for r in read_jsonl("preds/val_llmsel_trace.jsonl")}
control = {r["query_id"]: r for r in read_jsonl("preds/val_control.jsonl")}
client = GeminiClient(rpm=14, timeout_seconds=180)
solver = VisualTableSolver(client, PDFFetcher())

def cells(gold_table, rows, schema):
    keys = [c["name"] for c in schema if c.get("is_row_key")] or [schema[0]["name"]]
    graded = [(str(c["name"]), str(c.get("type","string"))) for c in schema
              if not c.get("is_row_key") and c.get("name")]
    gmap = {tuple(normalize_text(r.get(k)) for k in keys): r for r in gold_table["rows"]}
    pmap = {tuple(normalize_text(r.get(k)) for k in keys): r for r in rows}
    ok = tot = 0
    for key, grow in gmap.items():
        prow = pmap.get(key)
        for name, typ in graded:
            tot += 1
            if prow is not None and cell_equal(grow.get(name), prow.get(name), typ): ok += 1
    return (prf(set(gmap), set(pmap))[2], ok/tot if tot else 0.0, tot)

rowb=[];cellb=[];rowa=[];cella=[]
for qid, g in gold.items():
    if "table" not in g["answer_types"]: continue
    q=qs[qid]; schema=g["answer"]["table"]["schema"]
    t=traces.get(qid,{})
    rds=[Reading(r["paper_id"],r["found"],r["answer"],"",r["confidence"],r.get("evidence") or [])
         for r in t.get("readings",[])]
    papers=[pool[p] for p in t.get("paper_ids",[]) if p in pool.by_id]
    rf,ca,_=cells(g["answer"]["table"], control[qid]["answer"]["table"]["rows"], schema)
    rowb.append(rf); cellb.append(ca)
    out=solver.solve(q, rds, papers, pool.by_id)
    if out is None:
        rowa.append(rf); cella.append(ca); print(f"  {qid}: no pages -> fell back"); continue
    cols={str(c.get("name")):str(c.get("type","string")) for c in (q.table_schema or [])}
    fixed=[_conform_row(r, cols) for r in out["rows"]]
    rf2,ca2,_=cells(g["answer"]["table"], fixed, schema)
    rowa.append(rf2); cella.append(ca2)
    print(f"  {qid}: row {rf:.2f}->{rf2:.2f}  cell {ca:.2f}->{ca2:.2f}")
print(f"\nrow F1   {np.mean(rowb):.4f} -> {np.mean(rowa):.4f}  ({np.mean(rowa)-np.mean(rowb):+.4f})")
print(f"cell acc {np.mean(cellb):.4f} -> {np.mean(cella):.4f}  ({np.mean(cella)-np.mean(cellb):+.4f})")
print(f"overall contribution: {(np.mean(rowa)+np.mean(cella)-np.mean(rowb)-np.mean(cellb))/9:+.4f}")
print("usage:", client.usage)
