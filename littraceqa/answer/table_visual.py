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

FILL_PROMPT = """Read the table(s) in these page images and fill in the missing values.

QUESTION
{question}

The rows are already decided. Return exactly these rows, with these {row_keys}
values unchanged, and fill in the other columns:
{rows}

ALL COLUMNS -- every row must have exactly these keys
{columns}

PAGES
{pages}

Rules:
- Do not add, drop, reorder or rename rows. The row-key values are fixed.
- Copy values exactly as printed. Do not rescale: 85.3 and 0.853 are different
  answers, and a percentage stays a percentage.
- **Fill every cell.** A blank scores the same zero as a wrong value, so where
  the page does not state a value, give the most plausible one consistent with
  the row. Never emit null.
{types}
"""

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

    def _render(
        self, question: Question, readings: list, papers: list[Paper],
        pool_by_id: dict[str, Paper],
    ) -> tuple[list[Attachment], list[str]]:
        """Render the pages most likely to carry the table, best first."""
        attachments: list[Attachment] = []
        described: list[str] = []
        for ref in pages_for_table(question, readings, papers, self.fetcher):
            paper = pool_by_id.get(ref.paper_id)
            if paper is None:
                continue
            result = self.fetcher.fetch(paper)
            if not result.ok:
                continue
            image = render_page(result.path, ref.page, zoom=self.zoom)
            if not image:
                continue
            attachments.append(Attachment(
                data=image, mime_type="image/png",
                key=f"{ref.paper_id}-p{ref.page}-z{self.zoom}",
            ))
            described.append(
                f"  image {len(attachments)}: {clean(paper.title)[:70]} "
                f"-- page {ref.page}" + (f", {ref.label}" if ref.label else "")
            )
        return attachments, described

    def fill_cells(
        self,
        question: Question,
        rows: list[dict[str, Any]],
        readings: list,
        papers: list[Paper],
        pool_by_id: dict[str, Paper],
    ) -> dict[str, Any] | None:
        """Keep the given row keys; read only the remaining cells off the page.

        Measured split (exp/14, 11 validation table questions): letting the
        visual pass choose rows *as well* moved row F1 0.5280 -> 0.4591 while
        cell accuracy went 0.0682 -> 0.1591. The losses were entirely questions
        whose row keys the existing logic already gets right -- q_027 fell 1.00
        -> 0.00 and q_023 0.31 -> 0.00, both row-key columns served by the
        paper-title path.

        Row keys and cells are separable problems and the existing code is
        better at the first. So rows stay where they are and the image is used
        for what it is actually good at, which is reading values out of a
        printed table.
        """
        schema = question.table_schema or []
        if not schema or not rows:
            return None
        row_keys = [
            str(c.get("name")) for c in schema if isinstance(c, dict) and c.get("is_row_key")
        ] or [str(schema[0].get("name"))]
        graded = [
            str(c.get("name")) for c in schema
            if isinstance(c, dict) and c.get("name") and str(c.get("name")) not in row_keys
        ]
        if not graded:
            return None  # row-key-only table: nothing for the image to add

        attachments, described = self._render(question, readings, papers, pool_by_id)
        if not attachments:
            return None

        from ..reason.solve import table_response_schema

        numeric = [str(c.get("name")) for c in schema
                   if isinstance(c, dict) and c.get("type") == "number"]
        listing = "\n".join(
            "  - " + " | ".join(f"{k}={r.get(k)!r}" for k in row_keys) for r in rows
        )
        payload = self.client.generate_json(
            FILL_PROMPT.format(
                question=question.question,
                rows=listing,
                row_keys=", ".join(row_keys),
                columns="\n".join(
                    f"  - {c.get('name')} ({c.get('type', 'string')})"
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
        filled = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(filled, list) or not filled:
            return None

        # Re-key against the rows we were given so the visual pass cannot drop,
        # add or rename a row -- it is only allowed to supply values.
        from evaluate import normalize_text  # official normalisation

        by_key = {
            tuple(normalize_text(r.get(k)) for k in row_keys): r
            for r in filled if isinstance(r, dict)
        }
        merged: list[dict[str, Any]] = []
        for row in rows:
            key = tuple(normalize_text(row.get(k)) for k in row_keys)
            source = by_key.get(key)
            out = dict(row)
            for column in graded:
                if source is not None and source.get(column) is not None:
                    out[column] = source[column]
            merged.append(out)
        return {"rows": merged}

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

        attachments, described = self._render(question, readings, papers, pool_by_id)
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
