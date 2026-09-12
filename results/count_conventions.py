#!/usr/bin/env python3
"""Recompute every support count in the paper's annotation-convention table
directly from the 55 released development examples and the cached paper PDFs.

Source of truth: data/validation.jsonl (gold) + pdf_cache/*.pdf (page text),
with the evaluator's own key functions imported from scripts/evaluate.py.
Nothing here is counted by hand.

Usage:  .venv/bin/python results/count_conventions.py
"""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate as E  # noqa: E402

import pymupdf  # noqa: E402

VAL = [json.loads(l) for l in open(ROOT / "data" / "validation.jsonl")]
PDF = ROOT / "pdf_cache"
assert len(VAL) == 55, len(VAL)

_pages: dict[str, list[str]] = {}


def pages(paper_id: str):
    """Page text for a paper, or None when the PDF was never fetched."""
    if paper_id not in _pages:
        f = PDF / f"{paper_id}.pdf"
        if not f.exists():
            _pages[paper_id] = None
        else:
            with pymupdf.open(f) as doc:
                _pages[paper_id] = [p.get_text() for p in doc]
    return _pages[paper_id]


rows, notes = {}, {}

# ---------------------------------------------------------------- 1. evidence
# Two readings of "exactly one evidence key per gold paper":
#   bijective  - every gold paper carries exactly one key and no key is orphaned
#   cardinality- the number of distinct keys equals the number of gold papers
bij = card = 0
dist = collections.Counter()
for r in VAL:
    keys, papers = E.evidence_set(r), E.paper_id_set(r)
    dist[(len(papers), len(keys))] += 1
    per = collections.Counter(k[0] for k in keys)
    bij += bool(per) and set(per) == papers and all(c == 1 for c in per.values())
    card += len(keys) == len(papers)
rows["one_key_per_paper_bijective"] = (bij, 55)
rows["one_key_per_paper_cardinality"] = (card, 55)
notes["(papers,keys) histogram"] = {f"{k[0]},{k[1]}": v for k, v in sorted(dist.items())}
notes["cardinality-but-not-bijective"] = card - bij
notes["...all of shape"] = "4 gold papers, 4 keys, one paper carrying 2 keys and one cited by none"

# ------------------------------------------------------------------ 2. tables
# Gold table rows == gold paper count, on multi-paper table questions.
hit = tot = 0
allhit = alltot = 0
for r in VAL:
    if "table" not in (r.get("answer_types") or []):
        continue
    npap = len(E.paper_id_set(r))
    nrow = len(((r.get("answer") or {}).get("table") or {}).get("rows") or [])
    alltot += 1
    allhit += npap == nrow
    if npap >= 2:
        tot += 1
        hit += npap == nrow
rows["rows_eq_papers_multipaper"] = (hit, tot)
rows["rows_eq_papers_all_table_qs"] = (allhit, alltot)

# ------------------------------------------------- 3-5. wording implies a type
WORDING = {
    "figure": r"\bfigures?\b|\bfig\.|\bplots?\b|\bcharts?\b|\billustrat",
    "table": r"\btables?\b|\btab\.",
    "equation_algorithm": r"\bequations?\b|\bformula|\bloss\b|\bobjective\b|\balgorithm",
}
for typ, pat in WORDING.items():
    rx = re.compile(pat, re.I)
    hit = tot = 0
    for r in VAL:
        ev = r.get("evidence") or []
        if not ev or not rx.search(r["question"]):
            continue
        tot += 1
        hit += typ in {i["source_type"] for i in ev}
    rows[f"wording_implies_{typ}"] = (hit, tot)

# --------------------------------------- 6. table caption on the cited page
# Strict line-start caption, the form the shipped check used.
CAP = re.compile(r"^\s*Table\s*\d+[a-z]?\s*[:.]", re.I | re.M)
hit = tot = skipped = 0
for r in VAL:
    for it in r.get("evidence") or []:
        pg = (it.get("locator") or {}).get("page")
        pp = pages(it["paper_id"])
        if pp is None:
            skipped += 1
            continue
        if not isinstance(pg, int) or not (1 <= pg <= len(pp)):
            continue
        if CAP.search(pp[pg - 1]):
            tot += 1
            hit += it["source_type"] == "table"
rows["caption_on_page_implies_table"] = (hit, tot)
notes["items skipped, PDF never fetched"] = skipped

# ------------------------------- 7. text_span paired with a same-page object
for label, want in (("table", {"table"}), ("any object", None)):
    paired = objs = 0
    for r in VAL:
        ev = r.get("evidence") or []
        spans = {(i["paper_id"], (i.get("locator") or {}).get("page"))
                 for i in ev if i["source_type"] == "text_span"}
        for i in ev:
            st = i["source_type"]
            if st == "text_span" or (want and st not in want):
                continue
            objs += 1
            paired += (i["paper_id"], (i.get("locator") or {}).get("page")) in spans
    rows[f"text_span_paired_with_{label.replace(' ', '_')}"] = (paired, objs)

# ------------------------------------ 8. is the gold page the earliest match?
NUM = re.compile(r"\d+\.\d+|\d{1,3}(?:,\d{3})+|\d{2,}")
YEARS = {"2019", "2020", "2021", "2022", "2023", "2024", "2025"}


def answer_values(r):
    out = []
    ans = r.get("answer") or {}
    for row in ((ans.get("table") or {}).get("rows") or []):
        cells = row.get("cells") if isinstance(row, dict) else None
        for v in (cells or row if isinstance(row, dict) else {}).values() \
                if isinstance(cells or row, dict) else []:
            out += NUM.findall(str(v))
    ff = (ans.get("freeform") or {}).get("text")
    if ff:
        out += NUM.findall(ff)
    for it in r.get("evidence") or []:
        v = it.get("evidence_text_or_value")
        if v:
            out += NUM.findall(str(v))
    return [v for v in dict.fromkeys(out) if v not in YEARS]


pos = collections.Counter()
for r in VAL:
    vv = answer_values(r)
    if not vv:
        continue
    for it in r.get("evidence") or []:
        gp = (it.get("locator") or {}).get("page")
        pp = pages(it["paper_id"])
        if pp is None or not isinstance(gp, int):
            continue
        flat = [re.sub(r"\s+", "", p) for p in pp]
        hits = sorted({i + 1 for i, t in enumerate(flat) for v in vv if v in t})
        if gp not in hits or len(hits) < 2:
            continue
        i = hits.index(gp)
        pos["earliest" if i == 0 else "latest" if i == len(hits) - 1 else "middle"] += 1
n = sum(pos.values())
for k in ("earliest", "middle", "latest"):
    rows[f"gold_page_is_{k}_occurrence"] = (pos[k], n)

# ------------------------------------------------------- corpus-level totals
ev = [i for r in VAL for i in (r.get("evidence") or [])]
notes["dev questions"] = len(VAL)
notes["gold evidence items"] = len(ev)
notes["evidence items by source_type"] = dict(
    collections.Counter(i["source_type"] for i in ev))
pg = collections.Counter((i.get("locator") or {}).get("page") for i in ev)
notes["items on pages 6-7"] = pg[6] + pg[7]
notes["items on page 1"] = pg[1]
notes["distinct papers cited"] = len({i["paper_id"] for i in ev})

w = max(len(k) for k in rows)
for k, (a, b) in rows.items():
    print(f"{k:<{w}}  {a}/{b}" + (f"  = {a/b:.3f}" if b else ""))
print()
for k, v in notes.items():
    print(f"{k:<{w}}  {v}")

(Path(__file__).parent / "convention_counts.json").write_text(
    json.dumps({"counts": {k: list(v) for k, v in rows.items()}, "notes": notes},
               indent=1) + "\n")
