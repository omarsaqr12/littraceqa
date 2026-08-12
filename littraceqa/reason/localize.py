"""Read one paper and return both the answer fragment and its evidence locator.

The evaluator's evidence key is coarse:

    (paper_id, source_type, str(page), object_id)

so the model only needs to name the page and the visible object ("Table 4",
"Figure 2", "Equation 6", citation number) -- never a row, column, region, or
sentence offset. The prompt is written to that key exactly: asking for less
than the gold schema carries is what makes this reliable.

`source_type` is elicited explicitly rather than inferred, because it is a
graded field: naming the right page but calling a table a text_span scores zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..corpus import Paper, Question
from ..textnorm import clean
from .client import Attachment, GeminiClient

SOURCE_TYPES = ("table", "figure", "text_span", "citation_context", "equation_algorithm")

#: Mirrors schema/submission.schema.json -- locator keys outside this set are
#: rejected by the official validator (additionalProperties: false).
LOCATOR_KEYS = {
    "table": "table_id",
    "figure": "figure_id",
    "equation_algorithm": "equation_id",
    "citation_context": "citation_id",
    "text_span": None,
}

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "quote": {"type": "string"},
        "confidence": {"type": "number"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_type": {"type": "string", "enum": list(SOURCE_TYPES)},
                    "page": {"type": "integer"},
                    "object_id": {"type": "string"},
                    "section": {"type": "string"},
                },
                "required": ["source_type", "page"],
            },
        },
    },
    "required": ["found", "answer", "confidence", "evidence"],
}

PROMPT = """You are reading one paper from a scientific-literature QA benchmark.

PAPER
  id:    {paper_id}
  title: {title}
  venue: {venue} {year}

QUESTION
{question}

Answer the question using ONLY this PDF. Then say exactly where in the PDF the
answer comes from.

Rules for the evidence you report:
- `page` is the page number **as printed in this PDF**, counting the first page
  as 1. Get this right; it is graded.
- `source_type` must be the kind of object the value is actually read from:
    table               a value inside a results table
    figure              a value read off a plot, a figure panel, or its caption
    equation_algorithm  a formula, symbol definition, or algorithm block
    citation_context    a reference-list entry or an inline citation
    text_span           running prose (use only when none of the above fit)
- `object_id` is the visible label of that object, verbatim: "Table 4",
  "Figure 2", "Equation 6". For citation_context give the reference number
  alone, e.g. "24". For text_span leave it empty.
- Report one evidence item per distinct location the answer needs. Usually one.
  Do not pad the list; precision is graded as well as recall.

If this paper does not contain the answer, set found=false, answer="", and
evidence=[]. Do not guess, and do not use knowledge from outside the PDF.

`answer` must be the value alone, with no explanation: "14.70", "Freda Shi",
"8", "a single NVIDIA RTX 4090 GPU".
`quote` is the sentence or cell text you read it from.
`confidence` is 0.0-1.0 for how certain you are.
"""


@dataclass(slots=True)
class Reading:
    paper_id: str
    found: bool
    answer: str
    quote: str
    confidence: float
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_evidence_records(self, trust_pages: bool = True) -> list[dict[str, Any]]:
        """Schema-exact evidence records for the submission file."""
        records = []
        for item in self.evidence:
            source_type = str(item.get("source_type") or "").strip()
            if source_type not in SOURCE_TYPES:
                continue
            locator: dict[str, Any] = {}
            page = item.get("page")
            if trust_pages and isinstance(page, int) and page >= 1:
                locator["page"] = page
            key = LOCATOR_KEYS[source_type]
            object_id = normalize_object_id(item.get("object_id"), source_type)
            if key and object_id:
                locator[key] = object_id
            if not locator and (section := str(item.get("section") or "").strip()):
                locator["section"] = section
            if not locator:
                continue  # the evaluator drops keyless evidence anyway
            records.append(
                {"paper_id": self.paper_id, "source_type": source_type, "locator": locator}
            )
        return records


_NUMBERED = re.compile(r"^(table|figure|fig|equation|eq|algorithm|alg)\.?\s*(\d+[a-z]?)$", re.I)
_CANONICAL = {
    "table": "Table", "figure": "Figure", "fig": "Figure",
    "equation": "Equation", "eq": "Equation",
    "algorithm": "Algorithm", "alg": "Algorithm",
}


def normalize_object_id(value: Any, source_type: str) -> str:
    """Canonicalise to the surface form gold uses ("Table 4", "Figure 2", "24").

    `evaluate.normalize_visible_id` lowercases and accepts a bare number, so
    "table 4" / "Table 4" / "4" all collapse to the same key for tables. Emitting
    the canonical form anyway keeps the file readable and survives a stricter
    official evaluator.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if source_type == "citation_context":
        digits = re.findall(r"\d+", text)
        return digits[0] if digits else text
    if match := _NUMBERED.match(text):
        return f"{_CANONICAL[match.group(1).lower()]} {match.group(2)}"
    if text.isdigit():
        prefix = {"table": "Table", "figure": "Figure",
                  "equation_algorithm": "Equation"}.get(source_type, "")
        return f"{prefix} {text}".strip()
    return text


class PaperReader:
    """One LLM call per (question, paper), with the whole PDF as context."""

    def __init__(self, client: GeminiClient, *, max_output_tokens: int = 4096):
        self.client = client
        self.max_output_tokens = max_output_tokens

    def read(
        self, question: Question, paper: Paper, pdf_path: Path, *, trust_pages: bool = True
    ) -> Reading:
        try:
            data = pdf_path.read_bytes()
        except OSError as exc:
            return Reading(paper.paper_id, False, "", "", 0.0, error=f"unreadable pdf: {exc}")
        prompt = PROMPT.format(
            paper_id=paper.paper_id,
            title=clean(paper.title),
            venue=paper.venue,
            year=paper.year,
            question=question.question,
        )
        payload = self.client.generate_json(
            prompt,
            schema=READ_SCHEMA,
            attachments=[Attachment(data=data, key=paper.paper_id)],
            max_output_tokens=self.max_output_tokens,
            default=None,
        )
        if not isinstance(payload, dict):
            return Reading(paper.paper_id, False, "", "", 0.0, error="unparseable response")

        evidence = payload.get("evidence")
        reading = Reading(
            paper_id=paper.paper_id,
            found=bool(payload.get("found")),
            answer=str(payload.get("answer") or "").strip(),
            quote=str(payload.get("quote") or "").strip(),
            confidence=float(payload.get("confidence") or 0.0),
            evidence=[e for e in (evidence or []) if isinstance(e, dict)],
        )
        if not trust_pages:
            # PDF came from an arXiv fallback; its pagination is not the venue's.
            for item in reading.evidence:
                item.pop("page", None)
        return reading
