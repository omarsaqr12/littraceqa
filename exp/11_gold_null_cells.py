"""E6 -- how often is a gold table cell actually null?

`cell_equal` returns True for null only when gold is *also* null, so a wrong
guess and a null score identically against non-null gold. Guessing therefore
weakly dominates, and `TABLE_PROMPT`'s "Use null for a cell you genuinely cannot
determine" is a strict loss on every non-null gold cell.

That argument only holds if gold nulls are rare. Measure before deleting.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from littraceqa.corpus import load_gold

gold = load_gold()

total = nulls = 0
per_column: dict[str, list[int]] = collections.defaultdict(list)
per_question: list[tuple[str, int, int]] = []

for query_id, record in gold.items():
    table = record.get("answer", {}).get("table")
    if not isinstance(table, dict):
        continue
    schema = table.get("schema") or []
    row_keys = {c["name"] for c in schema if isinstance(c, dict) and c.get("is_row_key")}
    graded = [
        str(c.get("name")) for c in schema
        if isinstance(c, dict) and c.get("name") and c["name"] not in row_keys
    ]
    if not graded:
        continue  # row-key-only table: no cells are graded at all
    q_total = q_null = 0
    for row in table.get("rows") or []:
        for column in graded:
            value = row.get(column)
            total += 1
            q_total += 1
            is_null = value is None
            nulls += is_null
            q_null += is_null
            per_column[column].append(int(is_null))
    per_question.append((query_id, q_null, q_total))

print(f"graded (non-row-key) gold cells: {total}")
print(f"null among them:                 {nulls}")
print(f"gold null rate:                  {nulls / total:.1%}" if total else "n/a")

print("\n=== per question ===")
for query_id, q_null, q_total in per_question:
    flag = "  <-- all null" if q_null == q_total and q_total else ""
    print(f"  {query_id}: {q_null}/{q_total} null{flag}")

print("\n=== per column ===")
for column, flags in sorted(per_column.items(), key=lambda kv: -sum(kv[1])):
    rate = sum(flags) / len(flags)
    print(f"  {rate:>6.1%}  ({sum(flags)}/{len(flags)})  {column}")

print("\n=== verdict ===")
rate = nulls / total if total else 0.0
if rate < 0.10:
    print(f"  {rate:.1%} < 10%: delete the null instruction from TABLE_PROMPT and force a")
    print("  guess. Also fix _conform_row, which nulls type-mismatched cells regardless")
    print("  of what the prompt says -- the prompt alone is not sufficient.")
elif rate > 0.25:
    print(f"  {rate:.1%} > 25%: keep nulls, but only for the columns listed above.")
else:
    print(f"  {rate:.1%}: in between. Guessing still weakly dominates on the {1-rate:.0%}")
    print("  of cells that are non-null; prefer guessing but keep null for columns")
    print("  with a high individual rate.")
