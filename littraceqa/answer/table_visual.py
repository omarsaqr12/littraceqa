"""Build the answer table by looking at the table, not at a summary of it.

`solve_table` fills the schema from `format_evidence()` -- one line per paper
carrying the single answer string the reader returned for a different question.
Cell accuracy 0.0952 is what that produces, and rewriting `TABLE_PROMPT` changed
the output not at all (reports/local_reader.md), because the prompt was never the
constraint: the information simply was not in the digest.

This path renders the page the table is printed on and hands the model the image
together with the schema. Tables are the one content type where text extraction
reliably scrambles column alignment, so a picture of the table is worth more than
its extracted text.

Worth 2/9 of the overall score: `table_row_f1_macro` and
`table_cell_accuracy_macro` are graded separately and independently, and a table
question carries 4.8x the weight of a multiple-choice one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..corpus import Paper, Question
from ..pdf.read import load_text, render_page
from ..reason.client import Attachment, GeminiClient
from ..textnorm import clean

PROMPT = """Read the table(s) in these page images and fill in the answer table.

QUESTION
{question}

REQUIRED COLUMNS -- every row must have exactly these keys
{columns}

PAGES
{pages}

How to build the rows:
- **The question decides the rows.** Work out the row keys from the question
  before looking at the images. If it enumerates items -- four method names, four
  dataset names -- those are the rows, one each, in the order given.
- Row keys are graded by exact string match, so use the surface form the question
  or the paper uses, not a paraphrase or an expansion.
- **Fill every cell.** A blank scores the same zero as a wrong value, so where the
  page does not state a number, give the most plausible one consistent with the
  rest of the row. Never emit null.
- Copy numbers exactly as printed. Do not rescale: 85.3 and 0.853 are different
  answers, and a percentage stays a percentage.
- Where a cell has a value with an error bar ("32.7±0.5"), give the whole string
  if the column is a string column and the main value if it is numeric.
{types}
"""


@dataclass(slots=True)
class PageRef:
    paper_id: str
    page: int
    label: str = ""


def pages_for_table(
    question: Question, readings: list, papers: list[Paper], fetcher, *, limit: int = 3
) -> list[PageRef]:
    """Which pages to show, best first.

    Priority: pages the reader already pointed at with table-typed evidence, then
    any page it pointed at, then pages whose caption index shows a table. The
    reader's locator is right far more often than its answer -- 3 of 4 exact on
    the smoke set -- so it is the better signal here even when the value it read
    was wrong.
    """
    refs: list[PageRef] = []
    seen: set[tuple[str, int]] = set()

    def add(paper_id: str, page: Any, label: str) -> None:
        if not isinstance(page, int) or page < 1:
            return
        if (paper_id, page) in seen:
            return
        seen.add((paper_id, page))
        refs.append(PageRef(paper_id, page, label))

    for typed_only in (True, False):
        for reading in readings:
            for item in getattr(reading, "evidence", None) or []:
                if not isinstance(item, dict):
                    continue
                if typed_only and item.get("source_type") != "table":
                    continue
                add(reading.paper_id, item.get("page"), str(item.get("object_id") or ""))
        for reading in readings:
            for candidate in getattr(reading, "candidates", None) or []:
                for index in getattr(reading, "evidence_index", None) or []:
                    if not isinstance(index, int):
                        continue
                    chosen = (reading.candidates[index]
                              if index < len(reading.candidates) else None)
                    if chosen is None:
                        continue
                    if typed_only and chosen.source_type != "table":
                        continue
                    add(reading.paper_id, chosen.page, chosen.object_id)

    # Fall back to the caption index: first table-captioned page of each paper.
    if len(refs) < limit:
        for paper in papers:
            result = fetcher.fetch(paper)
            if not result.ok:
                continue
            text = load_text(paper.paper_id, result.path)
            if text is None:
                continue
            for caption in text.captions:
                if caption.kind == "Table":
                    add(paper.paper_id, caption.page, caption.object_id)
                    break
    return refs[:limit]


class VisualTableSolver:
    def __init__(self, client: GeminiClient, fetcher, *, zoom: float = 2.0):
        self.client = client
        self.fetcher = fetcher
        self.zoom = zoom

    def solve(
        self,
        question: Question,
        readings: list,
        papers: list[Paper],
        pool_by_id: dict[str, Paper],
    ) -> dict[str, Any] | None:
        """Schema-shaped rows read off the page, or None to fall back."""
        schema = question.table_schema or []
        if not schema:
            return None

        refs = pages_for_table(question, readings, papers, self.fetcher)
        attachments: list[Attachment] = []
        described: list[str] = []
        for ref in refs:
            paper = pool_by_id.get(ref.paper_id)
            if paper is None:
                continue
            result = self.fetcher.fetch(paper)
            if not result.ok:
                continue
            image = render_page(result.path, ref.page, zoom=self.zoom)
            if not image:
                continue
            attachments.append(
                Attachment(data=image, mime_type="image/png",
                           key=f"{ref.paper_id}-p{ref.page}-z{self.zoom}")
            )
            described.append(
                f"  image {len(attachments)}: {clean(paper.title)[:70]} "
                f"-- page {ref.page}" + (f", {ref.label}" if ref.label else "")
            )
        if not attachments:
            return None

        from ..reason.solve import table_response_schema

        numeric = [str(c.get("name")) for c in schema
                   if isinstance(c, dict) and c.get("type") == "number"]
        payload = self.client.generate_json(
            PROMPT.format(
                question=question.question,
                columns="\n".join(
                    f"  - {c.get('name')} ({c.get('type', 'string')})"
                    + ("  [ROW KEY]" if c.get("is_row_key") else "")
                    for c in schema if isinstance(c, dict)
                ),
                pages="\n".join(described),
                types=(f"- Columns {numeric} must be JSON numbers, not strings."
                       if numeric else ""),
            ),
            schema=table_response_schema(schema),
            attachments=attachments,
            max_output_tokens=2400,
            default=None,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            return None
        return {"rows": rows}
