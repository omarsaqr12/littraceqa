#!/usr/bin/env python3
"""Cross-check the manuscript against the source-of-truth artifacts.

Parses paper/littraceqa_system.tex and verifies, mechanically:

  Table 3   every printed component against results/official_scores.csv, and
            every printed `overall` against the value recomputed from the
            official components, within a derived rounding tolerance.
  Table 2   every printed support count against results/convention_counts.json,
            which is regenerated from the 55 dev examples by count_conventions.py.
  Table 3   the stated row-selection rule (record-setting runs + the regression)
            and the stated counts of scored / listed / omitted submissions.
  Figure 2  that it is generated from official_scores.csv, and that the run set
            it plots matches the CSV.

Exit status is non-zero if any check fails.

Usage:  .venv/bin/python results/check_manuscript.py
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEX = (ROOT / "paper" / "littraceqa_system.tex").read_text()
# prose is compared with whitespace normalised, so line re-wrapping never
# breaks a check and never hides one.
FLAT = re.sub(r"\s+", " ", TEX)
SCORES = list(csv.DictReader(open(ROOT / "results" / "official_scores.csv")))
COUNTS = json.loads((ROOT / "results" / "convention_counts.json").read_text())["counts"]

fails, checks = [], 0


def check(ok, msg):
    global checks
    checks += 1
    if not ok:
        fails.append(msg)


def num(text):
    text = text.strip().replace(r"\textbf{", "").replace("}", "").strip()
    return None if text in {"---", "--", "—", ""} else float(text)


# ---------------------------------------------------------------- Table 3
body = TEX.split(r"\begin{tabular}{llrrrrrr}")[1].split(r"\end{tabular}")[0]
rows = []
for line in body.splitlines():
    line = line.strip()
    if not line or line.startswith("\\") or "&" not in line:
        continue
    cells = [c.strip() for c in line.rstrip("\\").split("&")]
    if len(cells) == 8 and re.fullmatch(r"v\d+", cells[0]):
        rows.append(cells)

by_run = {r["run"]: r for r in SCORES}
check(len(rows) == 18, f"Table 3 has {len(rows)} data rows, expected 18")

for cells in rows:
    run = cells[0]
    if run not in by_run:
        check(False, f"Table 3 row {run} is not in official_scores.csv")
        continue
    src = by_run[run]
    for col, key in ((2, "paper_f1"), (3, "evidence_f1"), (4, "mc"),
                     (5, "row_f1"), (6, "cell_acc"), (7, "overall_shown")):
        shown = num(cells[col])
        truth = src[key].strip()
        if not truth:
            check(shown is None,
                  f"Table 3 {run}/{key}: prints {shown} but the CSV records no value")
            continue
        check(shown is not None and abs(shown - round(float(truth), 4)) < 5e-9,
              f"Table 3 {run}/{key}: paper {shown} vs artifact {round(float(truth),4)}")
    # overall must be reproducible from the components, where all are present
    vals = [num(cells[c]) for c in (2, 3, 4, 5, 6)]
    if all(v is not None for v in vals):
        p, e, mc, ro, ce = vals
        rec = (p + e + (mc + ro + ce) / 3) / 3
        check(abs(rec - num(cells[7])) <= 9.45e-5,
              f"Table 3 {run}: overall {num(cells[7])} vs recomputed {rec:.6f}")

# selection rule stated in the caption
best, records = -1.0, []
for r in SCORES:
    o = float(r["overall_shown"])
    if o > best:
        best, _ = o, records.append(r["run"])
listed = [c[0] for c in rows]
check(set(listed) == set(records) | {"v55"},
      f"Table 3 rows are not exactly the record-setters plus v55: "
      f"missing {sorted(set(records)-set(listed))}, extra {sorted(set(listed)-set(records)-{'v55'})}")
for phrase, value in ((r"We made (\d+) scored submissions", len(SCORES)),
                      (r"listed here are the (\d+) that set a new", len(records)),
                      (r"The other (five|six|seven|four) explored", len(SCORES) - len(rows))):
    m = re.search(phrase, FLAT)
    check(m is not None, f"caption phrase not found: {phrase}")
    if m:
        got = m.group(1)
        words = {"four": 4, "five": 5, "six": 6, "seven": 7}
        check(words.get(got, None) == value if got in words else int(got) == value,
              f"caption says {got!r} where the artifacts give {value}")

# ---------------------------------------------------------------- Table 2
T2 = {
    "45/55": "one_key_per_paper_cardinality",
    "8/8": "rows_eq_papers_multipaper",
    "10/10": "wording_implies_figure",
    "3/3": "wording_implies_table",
    "4/7": "wording_implies_equation_algorithm",
    "52/68": "caption_on_page_implies_table",
    "1/64": "text_span_paired_with_table",
    "17/84": "gold_page_is_earliest_occurrence",
}
for printed, key in T2.items():
    a, b = COUNTS[key]
    check(f"{a}/{b}" == printed,
          f"Table 2 prints {printed} for {key}, artifacts give {a}/{b}")
    check(printed in FLAT, f"Table 2: {printed} ({key}) not found in the manuscript")
check("37/55" in FLAT, "the strict one-key-per-paper reading (37/55) is not stated")

# ---------------------------------------------------------------- Figure 2
fig = (ROOT / "paper" / "make_fig.py").read_text()
check("official_scores.csv" in fig, "make_fig.py no longer reads official_scores.csv")
check("fonttype\"] = 42" in fig, "make_fig.py no longer forces Type 42 fonts")
m = re.search(r"all (\d+) of our scored submissions", FLAT)
check(m and int(m.group(1)) == len(SCORES),
      f"Figure 2 caption submission count disagrees with the CSV ({len(SCORES)})")

# ---------------------------------------------------------------- report
print(f"{checks} checks, {len(fails)} failed")
for f in fails:
    print("  FAIL:", f)
sys.exit(1 if fails else 0)
