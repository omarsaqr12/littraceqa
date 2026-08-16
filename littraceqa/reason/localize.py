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
from ..pdf.objects import EvidenceCandidate, format_candidates
from ..pdf.read import shrink_pdf
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

#: Used instead of READ_SCHEMA when a candidate locator list is available. The
#: model picks indices into a list built from the PDF rather than generating a
#: page number and an object id of its own -- see `littraceqa/pdf/objects.py`.
#: The free-form `evidence` array is kept as a fallback for an out-of-range pick.
READ_SCHEMA_INDEXED = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "quote": {"type": "string"},
        "confidence": {"type": "number"},
        "label": {"type": "string"},
        "evidence_index": {"type": "array", "items": {"type": "integer"}},
        "evidence": READ_SCHEMA["properties"]["evidence"],
    },
    "required": ["found", "answer", "confidence", "evidence_index"],
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
    text_span           running prose (genuine last resort -- see below)
- `object_id` is the visible label of that object, verbatim: "Table 4",
  "Figure 2", "Equation 6". For citation_context give the reference number
  alone, e.g. "24". For text_span leave it empty.
- Report one evidence item per distinct location the answer needs. Usually
  exactly one: 18 of 26 comparable questions in this benchmark have a single
  gold evidence item. Do not pad the list; precision is graded as well as recall.
- **`text_span` is the rarest answer, not the safest.** Measured over this
  benchmark's gold evidence, the source type is a table 31% of the time, a
  figure 27%, running prose only 16%, a reference 13%, an equation 13%. Prose is
  the least likely of the five. A reported number, score, or measurement almost
  always comes from a table or a figure even when the surrounding prose repeats
  it -- in that case the table or figure is the answer, not the sentence. Choose
  `text_span` only when the value genuinely appears in no table, figure,
  equation or reference anywhere in the paper.

Always name the single most likely location, even when you are unsure. There is
no credit for abstaining: the scorer gives an empty evidence list exactly the
same zero as a wrong one, so a low-confidence guess is free upside. If you cannot
find the answer, set found=false but still report your best guess at the location
in `evidence` and say how unsure you are in `confidence`. Never return an empty
`evidence` list. Do not use knowledge from outside the PDF.

`answer` must be the value alone, with no explanation: "14.70", "Freda Shi",
"8", "a single NVIDIA RTX 4090 GPU".
`quote` is the sentence or cell text you read it from.
`confidence` is 0.0-1.0 for how certain you are.
"""

#: Appended to either prompt when the question is multiple choice. Asking for the
#: label in the *same* call as the read is what stops the answer being laundered
#: through a text digest: the previous two-call path had the reader extract a
#: value while blind to the options, then had the solver pick an option while
#: blind to the PDF.
OPTIONS_BLOCK = """

MULTIPLE-CHOICE OPTIONS
{options}

Also set `label` to the letter of the option your reading supports. Judge the
options against what this PDF actually says, not against your recollection.
Commit to a letter even if the match is imperfect -- there is no credit for
abstaining. If this paper genuinely cannot settle the question, still give the
closest letter and lower `confidence`."""

CANDIDATES_BLOCK = """

CANDIDATE LOCATIONS IN THIS PDF
These were extracted mechanically from the PDF: the page numbers are exact and
the object labels are the ones actually printed in it.

{candidates}

Set `evidence_index` to the indices of the entries the answer comes from --
usually one, and never more than you need, since precision is graded too. Choose
the most specific entry that fits: prefer the table/figure/equation the value is
printed in over the page's prose entry. Only fall back to the free-form
`evidence` field if no entry above fits at all."""


@dataclass(slots=True)
class Reading:
    paper_id: str
    found: bool
    answer: str
    quote: str
    confidence: float
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    #: Multiple-choice label, when the reader was given the options (see
    #: OPTIONS_BLOCK). Empty when it was not asked.
    label: str = ""
    #: Locators enumerated from the PDF, and the model's picks into that list.
    #: When both are present the locator is built from the PDF, not from model
    #: output -- the page is then exact by construction.
    candidates: list[EvidenceCandidate] = field(default_factory=list)
    evidence_index: list[int] = field(default_factory=list)

    def to_evidence_records(self, trust_pages: bool = True) -> list[dict[str, Any]]:
        """Schema-exact evidence records for the submission file."""
        # Preferred path: the model picked entries out of a list we built from
        # the PDF, so page and object id are both transcriptions rather than
        # generations. Falls through to the free-form path when no pick is valid.
        picked = [
            self.candidates[i]
            for i in self.evidence_index
            if isinstance(i, int) and 0 <= i < len(self.candidates)
        ]
        if picked:
            return [c.to_evidence_record(self.paper_id) for c in picked]

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


def _clean_label(value: Any) -> str:
    """First standalone capital letter in the model's answer ("(C)" -> "C")."""
    text = str(value or "").strip().upper()
    if not text:
        return ""
    match = re.search(r"\b([A-Z])\b", text)
    return match.group(1) if match else text[:1]


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
        self,
        question: Question,
        paper: Paper,
        pdf_path: Path,
        *,
        trust_pages: bool = True,
        options: dict[str, str] | None = None,
        candidates: list[EvidenceCandidate] | None = None,
    ) -> Reading:
        """One call per (question, paper).

        `options` folds the multiple-choice decision into this call rather than a
        second one against a text digest. `candidates` (from
        `littraceqa/pdf/objects.py`) turns locator reporting into a choice from
        the PDF's own contents instead of free generation.
        """
        try:
            data = pdf_path.read_bytes()
        except OSError as exc:
            return Reading(paper.paper_id, False, "", "", 0.0, error=f"unreadable pdf: {exc}")
        # Keep every paper on the inline upload path; the Files API hangs.
        data = shrink_pdf(data, self.client.INLINE_LIMIT)
        if len(data) > self.client.INLINE_LIMIT:
            return Reading(paper.paper_id, False, "", "", 0.0,
                           error=f"pdf still {len(data)//1024//1024}MB after shrinking")
        prompt = PROMPT.format(
            paper_id=paper.paper_id,
            title=clean(paper.title),
            venue=paper.venue,
            year=paper.year,
            question=question.question,
        )
        candidates = list(candidates or [])
        schema = READ_SCHEMA
        if candidates:
            prompt += CANDIDATES_BLOCK.format(candidates=format_candidates(candidates))
            schema = READ_SCHEMA_INDEXED
        if options:
            prompt += OPTIONS_BLOCK.format(
                options="\n".join(f"  {label}. {options[label]}" for label in sorted(options))
            )
        payload = self.client.generate_json(
            prompt,
            schema=schema,
            attachments=[Attachment(data=data, key=paper.paper_id)],
            max_output_tokens=self.max_output_tokens,
            default=None,
        )
        if not isinstance(payload, dict):
            return Reading(paper.paper_id, False, "", "", 0.0, error="unparseable response")

        evidence = payload.get("evidence")
        picks = payload.get("evidence_index")
        reading = Reading(
            paper_id=paper.paper_id,
            found=bool(payload.get("found")),
            answer=str(payload.get("answer") or "").strip(),
            quote=str(payload.get("quote") or "").strip(),
            confidence=float(payload.get("confidence") or 0.0),
            evidence=[e for e in (evidence or []) if isinstance(e, dict)],
            label=_clean_label(payload.get("label")),
            candidates=candidates,
            evidence_index=[i for i in (picks or []) if isinstance(i, int)],
        )
        # `trust_pages` is deliberately NOT used to strip pages any more, even on
        # an arXiv fallback whose pagination is not the venue's. Gold carries a
        # page on 149/149 validation evidence items, so the evaluator's location
        # field is never "": dropping the page guarantees a mismatch, while a
        # possibly-wrong page at least *can* match. Stripping it also deletes
        # text_span evidence outright, since page is that type's only locator.
        # Kept on FetchResult for diagnostics.
        return reading
