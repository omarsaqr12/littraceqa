"""Prove the record builder satisfies the official validator on every split.

The v1 design emitted `answer.multiple_choice = {"label": ...}`, which the
validator rejects and the evaluator scores as 0. This test exists so that class
of failure is caught locally rather than on submission day.

Builds a degenerate-but-valid submission for validation and test, runs the
official `validate_submission.validate_submission`, and checks that the
evaluator's readers actually see the fields we emit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate import evidence_set, multiple_choice_prediction, paper_id_set
from littraceqa.answer.build import build_record, validate_records
from littraceqa.corpus import DATA_DIR, PaperPool, load_questions

pool = PaperPool.load()
paper_ids = {p.paper_id for p in pool.papers}
sample = pool.papers[0].paper_id
failures = 0

for split, filename in [("validation", "validation_inputs.jsonl"), ("test", "test.jsonl")]:
    questions = load_questions(DATA_DIR / filename)
    records = []
    for q in questions:
        options = q.multiple_choice_options or {}
        parts = {
            "freeform": "placeholder",
            "multiple_choice": sorted(options)[0] if options else "A",
            "table": {"rows": [
                {str(c["name"]): ("x" if c.get("type") == "string" else
                                  1 if c.get("type") == "number" else True)
                 for c in (q.table_schema or [])}
            ]},
        }
        records.append(build_record(
            q,
            [sample],
            [{"paper_id": sample, "source_type": "table",
              # `row`/`column` are in gold but forbidden in submissions -- the
              # builder must strip them rather than pass them through.
              "locator": {"page": 3, "table_id": "Table 2", "row": "r", "column": "c"}}],
            parts,
        ))

    errors = validate_records(records, questions, paper_ids)
    status = "OK" if not errors else f"{len(errors)} ERROR(S)"
    print(f"{split:<12} {len(records):>4} records  official validator: {status}")
    for error in errors[:8]:
        print(f"    - {error}")
    failures += len(errors)

    # The evaluator must actually read what we wrote.
    probe = records[0]
    assert paper_id_set(probe) == {sample}, "evaluator cannot see gold_papers"
    keys = evidence_set(probe)
    assert keys == {(sample, "table", "3", "table 2")}, f"evidence key mismatch: {keys}"
    assert "row" not in probe["evidence"][0]["locator"], "forbidden locator key survived"

    mc = [r for r, q in zip(records, questions) if "multiple_choice" in q.answer_types]
    if mc:
        seen = multiple_choice_prediction(mc[0])
        expected = mc[0]["answer"]["multiple_choice"]["gold"]
        assert seen == expected, f"evaluator read {seen!r}, we wrote {expected!r}"
        assert set(mc[0]["answer"]["multiple_choice"]) == {"gold"}, "must be exactly {'gold'}"

print("\nevaluator round-trip: gold_papers, evidence key, and multiple_choice.gold all read back")
print("PASS" if failures == 0 else f"FAIL ({failures} validator errors)")
raise SystemExit(1 if failures else 0)
