"""Can local PDF parsing alone recover gold evidence pages?

The evidence key is (paper_id, source_type, page, object_id). For table/figure/
equation evidence, gold's object_id is a caption label ("Table 4"), and captions
are machine-findable. If a caption regex locates the right page, that part of
evidence F1 costs nothing and gives an independent check on the model's answer.

Measures, against gold evidence on validation:
  * caption page accuracy -- does `page_of("Table 4")` match gold's page?
  * reference page accuracy -- for citation_context, does the numbered entry land
    on gold's page?
  * reference text accuracy -- does entry N start with gold's cited author?
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from littraceqa.corpus import PaperPool, load_gold
from littraceqa.pdf.fetch import PDFFetcher
from littraceqa.pdf.read import load_text

pool = PaperPool.load()
gold = load_gold()
fetcher = PDFFetcher()

OBJECT_TYPES = {"table", "figure", "equation_algorithm"}
stats: Counter[str] = Counter()
mismatches: list[str] = []
cache: dict[str, object] = {}

targets = [
    (record["query_id"], item)
    for record in gold.values()
    for item in record["evidence"]
]
print(f"{len(targets)} gold evidence items across {len(gold)} questions\n")

for query_id, item in targets:
    paper_id = item["paper_id"]
    source_type = item["source_type"]
    locator = item.get("locator", {})
    gold_page = locator.get("page")

    if paper_id not in cache:
        result = fetcher.fetch(pool[paper_id])
        cache[paper_id] = (
            load_text(paper_id, result.path) if result.ok else None
        )
        stats["pdf_ok" if result.ok else "pdf_missing"] += 1
    text = cache[paper_id]
    if text is None:
        stats[f"{source_type}:no_pdf"] += 1
        continue

    if source_type in OBJECT_TYPES:
        object_id = (
            locator.get("table_id") or locator.get("figure_id")
            or locator.get("equation_id") or locator.get("algorithm_id") or ""
        )
        found = text.page_of(object_id)
        if found is None:
            stats[f"{source_type}:caption_not_found"] += 1
        elif found == gold_page:
            stats[f"{source_type}:page_correct"] += 1
        else:
            stats[f"{source_type}:page_wrong"] += 1
            if len(mismatches) < 10:
                mismatches.append(
                    f"  {query_id} {paper_id} {object_id!r}: regex p.{found}, gold p.{gold_page}"
                )
    elif source_type == "citation_context":
        number = locator.get("citation_id")
        try:
            number = int(number)
        except (TypeError, ValueError):
            stats["citation:bad_id"] += 1
            continue
        entry = text.references.get(number)
        stats["citation:entry_found" if entry else "citation:entry_missing"] += 1
        found = text.reference_page(number)
        stats["citation:page_correct" if found == gold_page else "citation:page_wrong"] += 1
        if entry:
            gold_text = str(item.get("evidence_text_or_value") or "")[:40].lower()
            first_author = gold_text.split(",")[0].strip()
            if first_author and first_author in entry.lower():
                stats["citation:text_matches_gold"] += 1
    else:
        stats["text_span:skipped (needs the model)"] += 1

print("results:")
for key, value in sorted(stats.items()):
    print(f"  {key:<42} {value}")

for kind in ("table", "figure", "equation_algorithm"):
    correct = stats[f"{kind}:page_correct"]
    total = correct + stats[f"{kind}:page_wrong"] + stats[f"{kind}:caption_not_found"]
    if total:
        print(f"\n{kind}: caption regex finds the gold page {correct}/{total} = {correct/total:.1%}")

if mismatches:
    print("\npage mismatches (regex vs gold):")
    print("\n".join(mismatches))
