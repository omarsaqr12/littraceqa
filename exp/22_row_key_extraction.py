"""Does deciding table row keys from the question alone beat the combined call?

Row F1 is a set F1 over row-key strings, graded by exact match after
`normalize_text`. The combined table call sees the papers' evidence and drifts to
the papers' wording; 44% of gold row keys appear verbatim in the question.

This isolates the row-key stage: no cells, no pipeline, just gold keys vs the
extractor vs what the shipped config actually emitted.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from littraceqa.corpus import DATA_DIR, load_questions
from littraceqa.reason.client import GeminiClient
from littraceqa.reason.solve import AnswerSolver, _is_title_column, _keys_grounded

spec = importlib.util.spec_from_file_location("ev", ROOT / "scripts" / "evaluate.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def main() -> None:
    gold = {r["query_id"]: r for r in ev.read_jsonl(DATA_DIR / "validation.jsonl")}
    shipped = {r["query_id"]: r for r in ev.read_jsonl(ROOT / "preds" / "val_cbsel.jsonl")}
    questions = {q.query_id: q for q in load_questions(DATA_DIR / "validation_inputs.jsonl")}

    solver = AnswerSolver(GeminiClient(), extract_row_keys=True)

    tot_new = tot_old = n = 0
    print(f"{'qid':<10} {'key column':<18} {'gold':>4} {'shipped F1':>11} {'extracted F1':>13}")
    for qid, record in gold.items():
        table = (record.get("answer") or {}).get("table")
        if not table:
            continue
        schema = table.get("schema") or []
        keys = [c["name"] for c in schema if c.get("is_row_key")] or [schema[0]["name"]]
        if len(keys) != 1:
            print(f"{qid:<10} {str(keys):<18} skipped (multi-key)")
            continue
        column = keys[0]
        gold_keys = {ev.row_key_value(r, keys) for r in table.get("rows") or []}

        old_rows = ((shipped.get(qid, {}).get("answer") or {}).get("table") or {}).get("rows") or []
        old_keys = {ev.row_key_value(r, keys) for r in old_rows}

        # Mirror the pipeline: a title column is pinned to pool titles and never
        # reaches the extractor; an ungrounded extraction falls back to the
        # combined call, whose output is exactly `shipped`.
        if _is_title_column(column):
            extracted, route = [], "title-pin (bypasses extractor)"
        else:
            extracted = solver._extract_row_keys(questions[qid], column) or []
            if extracted and _keys_grounded(questions[qid].question, extracted, column):
                route = "extractor (grounded)"
            else:
                extracted, route = [], "fallback (not grounded)"
        new_keys = ({ev.row_key_value(r, keys) for r in extracted}
                    if extracted else set(old_keys))

        _, _, f_old = ev.prf(gold_keys, old_keys)
        _, _, f_new = ev.prf(gold_keys, new_keys)
        tot_old += f_old
        tot_new += f_new
        n += 1
        flag = "  <-- better" if f_new > f_old + 1e-9 else ("  <-- WORSE" if f_new < f_old - 1e-9 else "")
        print(f"{qid:<10} {column:<18} {len(gold_keys):>4} {f_old:>11.3f} {f_new:>13.3f}{flag}   {route}")
        if f_new != f_old:
            print(f"           gold      : {sorted(k[0] for k in gold_keys)}")
            print(f"           extracted : {sorted(k[0] for k in new_keys)}")

    print(f"\nsingle-row-key validation table questions: n={n}")
    print(f"  shipped combined call : mean row F1 {tot_old/n:.4f}")
    print(f"  guarded extractor     : mean row F1 {tot_new/n:.4f}")
    print(f"  delta                 : {(tot_new-tot_old)/n:+.4f}")
    print(f"\nusage: {solver.client.usage}")


if __name__ == "__main__":
    main()
