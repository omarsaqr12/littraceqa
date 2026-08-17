"""E4 -- is our page numbering the same as the annotators'?

The evidence key grades `page` exactly, and gold carries a page on 149/149
validation items. If gold was built from a different rendering of the paper than
`pdf/fetch.py` returns -- arXiv preprint vs camera-ready vs proceedings PDF --
then every page is off by a constant and evidence F1 is capped no matter how
well the reader reads. That has never been measured.

Method: for every gold evidence item carrying an object id ("Table 4",
"Figure 2", "Equation 6"), find where that caption actually appears in our
fetched PDF and report `gold_page - our_page`. A caption is an unambiguous
anchor, so any systematic difference is an edition difference, not a reader
error.

Reads only local caches; makes no API calls.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from littraceqa.corpus import PaperPool, load_gold
from littraceqa.pdf.fetch import PDFFetcher
from littraceqa.pdf.read import load_text

OBJECT_KEYS = ("table_id", "figure_id", "equation_id", "algorithm_id")

pool = PaperPool.load()
gold = load_gold()
fetcher = PDFFetcher()

offsets: list[tuple[str, str, str, str, int, int, int]] = []
missing: list[tuple[str, str, str]] = []
no_pdf: set[str] = set()
text_cache: dict[str, object] = {}

for query_id, record in gold.items():
    for item in record.get("evidence", []):
        locator = item.get("locator") or {}
        gold_page = locator.get("page")
        object_id = next((locator[k] for k in OBJECT_KEYS if locator.get(k)), None)
        if not object_id or not isinstance(gold_page, int):
            continue
        paper_id = item["paper_id"]
        if paper_id not in text_cache:
            result = fetcher.fetch(pool[paper_id])
            text_cache[paper_id] = (
                load_text(paper_id, result.path) if result.ok else None
            )
            if not result.ok:
                no_pdf.add(paper_id)
        text = text_cache[paper_id]
        if text is None:
            continue

        found = text.page_of(str(object_id))
        venue = pool[paper_id].venue
        if found is None:
            missing.append((query_id, paper_id, str(object_id)))
            continue
        offsets.append(
            (query_id, paper_id, venue, str(object_id), gold_page, found, gold_page - found)
        )

print(f"anchored gold items: {len(offsets)}")
print(f"caption not found in our PDF: {len(missing)}")
print(f"papers with no fetchable PDF: {len(no_pdf)}")

if not offsets:
    raise SystemExit("no anchored items -- cannot audit")

delta_counts = collections.Counter(o[6] for o in offsets)
print("\n=== gold_page - our_page ===")
for delta, count in sorted(delta_counts.items()):
    bar = "#" * min(count, 60)
    print(f"  {delta:>+4}  {count:>4}  {bar}")

exact = delta_counts.get(0, 0)
print(f"\nexact agreement: {exact}/{len(offsets)} = {exact / len(offsets):.1%}")

print("\n=== by venue ===")
by_venue: dict[str, list[int]] = collections.defaultdict(list)
for _, _, venue, _, _, _, delta in offsets:
    by_venue[venue].append(delta)
for venue, deltas in sorted(by_venue.items(), key=lambda kv: -len(kv[1])):
    counts = collections.Counter(deltas)
    mode, mode_n = counts.most_common(1)[0]
    zero = counts.get(0, 0)
    print(f"  {venue:<9} n={len(deltas):>3}  zero={zero:>3} ({zero/len(deltas):>5.1%})  "
          f"mode={mode:+d} ({mode_n}/{len(deltas)})  spread={min(deltas):+d}..{max(deltas):+d}")

print("\n=== by fetch source ===")
by_source: dict[str, list[int]] = collections.defaultdict(list)
for _, paper_id, _, _, _, _, delta in offsets:
    by_source[fetcher.fetch(pool[paper_id]).source].append(delta)
for source, deltas in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
    counts = collections.Counter(deltas)
    zero = counts.get(0, 0)
    print(f"  {source:<11} n={len(deltas):>3}  zero={zero:>3} ({zero/len(deltas):>5.1%})  "
          f"mode={counts.most_common(1)[0][0]:+d}")

nonzero = [o for o in offsets if o[6] != 0]
if nonzero:
    print(f"\n=== sample disagreements ({len(nonzero)} total) ===")
    for query_id, paper_id, venue, object_id, gold_page, our_page, delta in nonzero[:15]:
        print(f"  {query_id} {paper_id:<20} {venue:<8} {object_id:<12} "
              f"gold p.{gold_page:<3} ours p.{our_page:<3} delta={delta:+d}")

print("\n=== verdict ===")
share = exact / len(offsets)
if share >= 0.95:
    print("  Pages agree. Alignment is NOT the cap; the reader is the constraint. -> E5.")
elif len(delta_counts) <= 2 and delta_counts.most_common(1)[0][0] != 0:
    print(f"  Systematic offset {delta_counts.most_common(1)[0][0]:+d}. Apply and re-score.")
else:
    print("  Mixed. Check the per-venue table above for a venue-specific edition problem.")
