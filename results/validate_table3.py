#!/usr/bin/env python3
"""Recompute the official `overall` from the official components of every scored
submission and compare with the overall the evaluator reported.

The evaluator (scripts/evaluate.py) defines

    answer  = (mc + row_f1 + cell_accuracy) / 3
    overall = (paper_f1 + evidence_f1 + answer) / 3

so the component weights are 1/3, 1/3, 1/9, 1/9, 1/9.

Rounding tolerance is derived, not guessed. Let d be the half-width of the
rounding interval of a displayed component (5e-5 at 4 dp, 0 when we hold the
evaluator's full-precision value). MC accuracy is a multiple of 1/50 over the 50
multiple-choice questions, so its 2 dp display is exact and contributes 0.

    |recomputed - true overall| <= (d_paper + d_evid + (0 + d_row + d_cell)/3)/3

and the reported overall is itself rounded to 4 dp, contributing a further 5e-5:

    tol = (d_paper + d_evid + (d_row + d_cell)/3)/3 + 5e-5

For a row stored at 4 dp that is 4.444e-5 + 5e-5 = 9.444e-5.
For a row stored at full precision it is 5e-5.

Usage:  .venv/bin/python results/validate_table3.py
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HALF = {"4dp": 5e-5, "full": 0.0}


def overall(paper, evid, mc, row, cell):
    return (paper + evid + (mc + row + cell) / 3) / 3


def tolerance(precision):
    d = HALF[precision]
    return (d + d + (d + d) / 3) / 3 + 5e-5


rows = list(csv.DictReader(open(HERE / "official_scores.csv")))
report, bad = [], []
incomplete = []
for r in rows:
    shown = float(r["overall_shown"])
    entry = dict(run=r["run"], file=r["file"], precision=r["precision"],
                 overall_official=shown, provenance=r["provenance"])
    missing = [k for k in ("paper_f1", "evidence_f1", "mc", "row_f1", "cell_acc")
               if not r[k].strip()]
    if missing:
        # A component the evaluator returned but we did not retain. The overall
        # is sourced; it simply cannot be recomputed. Never reconstruct it.
        incomplete.append((r["run"], missing))
        entry.update({k: (float(r[k]) if r[k].strip() else None)
                      for k in ("paper_f1", "evidence_f1", "mc", "row_f1", "cell_acc")})
        entry.update(overall_recomputed=None, difference=None, tolerance=None,
                     consistent=None, missing_components=missing)
        report.append(entry)
        continue
    p, e = float(r["paper_f1"]), float(r["evidence_f1"])
    mc, ro, c = float(r["mc"]), float(r["row_f1"]), float(r["cell_acc"])
    rec = overall(p, e, mc, ro, c)
    tol = tolerance(r["precision"])
    diff = rec - shown
    ok = abs(diff) <= tol
    if not ok:
        bad.append(r["run"])
    entry.update(paper_f1=p, evidence_f1=e, mc=mc, row_f1=ro, cell_acc=c,
                 overall_recomputed=round(rec, 8), difference=round(diff, 8),
                 tolerance=round(tol, 8), consistent=ok, missing_components=[])
    report.append(entry)

hdr = (f"{'run':<5} {'prec':<5} {'paper':>8} {'evid':>8} {'MC':>5} {'row':>8} "
       f"{'cell':>8} {'overall':>8} {'recomputed':>11} {'diff':>10} {'tol':>9}  verdict")
print(hdr)
print("-" * len(hdr))
def fmt(v, spec):
    return format(v, spec) if v is not None else "-" * len(format(0.0, spec))


for d in report:
    verdict = ("not checkable" if d["consistent"] is None
               else "ok" if d["consistent"] else "INCONSISTENT")
    print(f"{d['run']:<5} {d['precision']:<5} {fmt(d['paper_f1'],'8.6f')} "
          f"{fmt(d['evidence_f1'],'8.6f')} {fmt(d['mc'],'5.2f')} {fmt(d['row_f1'],'8.6f')} "
          f"{fmt(d['cell_acc'],'8.6f')} {d['overall_official']:8.4f} "
          f"{fmt(d['overall_recomputed'],'11.6f')} {fmt(d['difference'],'+10.6f')} "
          f"{fmt(d['tolerance'],'9.2e')}  {verdict}")

print(f"\n{len(report)} scored submissions, "
      f"{len(report) - len(incomplete)} fully checkable, {len(bad)} inconsistent"
      + (f": {', '.join(bad)}" if bad else ""))
for run, missing in incomplete:
    print(f"  {run}: not checkable, component(s) never retained: {', '.join(missing)}")
for d in report:
    if d["consistent"] is False:
        print(f"  {d['run']}: |diff| = {abs(d['difference']):.6f} "
              f"= {abs(d['difference'])/d['tolerance']:.1f}x its rounding tolerance")
        print(f"       provenance: {d['provenance']}")

(HERE / "table3_validation.json").write_text(json.dumps(report, indent=1) + "\n")
with open(HERE / "table3_validation.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(report[0]))
    w.writeheader()
    w.writerows(report)
print(f"\nwrote {HERE/'table3_validation.csv'} and .json")
