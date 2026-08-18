"""F2 -- why does table collapse from validation to test?

Test is easier than validation on paper, evidence and MC, and 2-3x WORSE on both
table metrics. Cell accuracy being gated by paper coverage is established
(q_030). Row F1 is not: row keys come from the question text, and paper selection
is *better* on test, so row F1 should have risen.

Pure measurement. Changes nothing, needs no gold, needs no submission -- the
table schema ships in the question input.
"""
from __future__ import annotations
import collections, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from littraceqa.corpus import DATA_DIR, load_questions
from littraceqa.reason.solve import _is_title_column

print("CONFIG: pure schema inspection, no model, no gold\n")

def survey(split: str, filename: str):
    qs = [q for q in load_questions(DATA_DIR / filename) if "table" in q.answer_types]
    print(f"=== {split}: {len(qs)} table questions ===")
    paths = collections.Counter()
    keyname = collections.Counter()
    keytype = collections.Counter()
    ncols = collections.Counter()
    nkeys = collections.Counter()
    for q in qs:
        schema = q.table_schema or []
        keys = [c for c in schema if c.get("is_row_key")]
        graded = [c for c in schema if not c.get("is_row_key")]
        nkeys[len(keys)] += 1
        ncols[len(schema)] += 1
        for c in keys:
            keyname[str(c.get("name"))] += 1
            keytype[str(c.get("type"))] += 1
        # which derivation path solve_table will take
        first = str(keys[0].get("name")) if keys else (
            str(schema[0].get("name")) if schema else "")
        if len(schema) == 1 and _is_title_column(first):
            paths["paper-title special case (rows = pool titles)"] += 1
        elif _is_title_column(first):
            paths["title-ish key BUT extra columns -> LLM digest"] += 1
        else:
            paths["LLM from evidence digest"] += 1
    print(f"  row-key count:  {dict(sorted(nkeys.items()))}")
    print(f"  column count:   {dict(sorted(ncols.items()))}")
    print(f"  row-key types:  {dict(keytype)}")
    print("  row-key names:")
    for n, c in keyname.most_common():
        print(f"      {c:>2}x {n!r}  {'<- title-ish' if _is_title_column(n) else ''}")
    print("  derivation path that fires:")
    for n, c in paths.most_common():
        print(f"      {c:>2}/{len(qs)}  {n}")
    return paths, len(qs)

vp, vn = survey("VALIDATION", "validation_inputs.jsonl")
print()
tp, tn = survey("TEST", "test.jsonl")

print("\n=== side by side: share of questions taking each path ===")
for path in set(vp) | set(tp):
    print(f"  {vp.get(path,0)/vn:>6.0%} val   {tp.get(path,0)/tn:>6.0%} test   {path}")
