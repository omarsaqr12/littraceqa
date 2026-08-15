"""Candidate evidence locators enumerated from the PDF itself.

The evaluator keys evidence on a 4-tuple:

    (paper_id, source_type, str(locator.page or locator.section), object_id)

Today both the page and the object id are *generated* by the reader model, which
means two independent chances to be wrong on a field that is graded exactly. The
measured shape of gold says that is the wrong division of labour:

* 149/149 validation gold evidence items carry a `page`. The location field is
  never empty, so any locator we emit without a page scores zero by construction.
* `table` (64), `figure` (18), `equation_algorithm` (7) and `citation_context`
  (6) gold items **always** carry an object id as well -- both halves must be
  right.
* `text_span` (54 items) **never** carries one. The page alone decides it.

All four of those object ids are printed in the PDF next to the thing they name,
and the page number is simply the index of the page they were printed on. So the
model should not be inventing them; it should be *choosing* from what the PDF
actually contains. This module enumerates the choices, and `page` comes from the
PyMuPDF page index rather than from any model output.

Everything here is local and free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .read import PaperText, load_text

#: `Caption.kind` -> the evaluator's `source_type`. Equations and algorithms
#: share one source_type but keep distinct locator keys (both are allowed by
#: the submission schema, and both normalise identically in the evaluator).
_KIND_TO_SOURCE = {
    "Table": "table",
    "Figure": "figure",
    "Equation": "equation_algorithm",
    "Algorithm": "equation_algorithm",
}
_KIND_TO_LOCATOR_KEY = {
    "Table": "table_id",
    "Figure": "figure_id",
    "Equation": "equation_id",
    "Algorithm": "algorithm_id",
}


@dataclass(slots=True)
class EvidenceCandidate:
    """One locator the PDF can actually support, ready to be scored."""

    source_type: str
    page: int
    object_id: str = ""
    #: Which locator key `object_id` belongs under ("table_id", ...). Empty for
    #: text_span, whose locator is the page alone.
    locator_key: str = ""
    #: Short caption/reference snippet, so the model can choose on content
    #: rather than on a bare number.
    context: str = ""

    def locator(self) -> dict[str, Any]:
        out: dict[str, Any] = {"page": self.page}
        if self.locator_key and self.object_id:
            out[self.locator_key] = self.object_id
        return out

    def to_evidence_record(self, paper_id: str) -> dict[str, Any]:
        return {
            "paper_id": paper_id,
            "source_type": self.source_type,
            "locator": self.locator(),
        }

    def describe(self) -> str:
        label = self.object_id or "prose"
        context = f" -- {self.context}" if self.context else ""
        return f"{self.source_type} | {label} | page {self.page}{context}"


def _caption_context(text: PaperText, page: int, object_id: str, chars: int = 110) -> str:
    """The caption line itself, trimmed, for disambiguating two same-numbered objects."""
    snippet = text.caption_text(object_id, chars=chars)
    return re.sub(r"\s+", " ", snippet).strip()


def objects_in_pdf(
    pdf_path: str | Path,
    paper_id: str = "",
    *,
    include_text_spans: bool = True,
    include_citations: bool = True,
    max_citations: int = 60,
) -> list[EvidenceCandidate]:
    """Every locator this PDF can support, with pages taken from the PDF.

    The page number is `PyMuPDF`'s 1-based page index throughout. It is never
    read from a model, and callers must not overwrite it with one.
    """
    text = load_text(paper_id, Path(pdf_path))
    if text is None:
        return []
    return candidates_from_text(
        text,
        include_text_spans=include_text_spans,
        include_citations=include_citations,
        max_citations=max_citations,
    )


def candidates_from_text(
    text: PaperText,
    *,
    include_text_spans: bool = True,
    include_citations: bool = True,
    max_citations: int = 60,
) -> list[EvidenceCandidate]:
    """`objects_in_pdf` for an already-parsed `PaperText`."""
    out: list[EvidenceCandidate] = []
    seen: set[tuple[str, int, str]] = set()

    def add(candidate: EvidenceCandidate) -> None:
        key = (candidate.source_type, candidate.page, candidate.object_id.lower())
        if key not in seen:
            seen.add(key)
            out.append(candidate)

    # 1. Captioned objects. `PaperText.captions` already regexes every page for
    #    "Table 4:", "Fig. 3", "Algorithm 1" and records the page it saw them on.
    for caption in text.captions:
        source_type = _KIND_TO_SOURCE.get(caption.kind)
        if not source_type:
            continue
        add(
            EvidenceCandidate(
                source_type=source_type,
                page=caption.page,
                object_id=caption.object_id,
                locator_key=_KIND_TO_LOCATOR_KEY[caption.kind],
                context=_caption_context(text, caption.page, caption.object_id),
            )
        )

    # 2. Numbered references. The evaluator keys citation_context on the number
    #    alone, so the reference list is the whole answer -- no GROBID needed.
    if include_citations:
        for number, entry in sorted(text.references.items())[:max_citations]:
            page = text.reference_page(number)
            if page is None:
                continue
            add(
                EvidenceCandidate(
                    source_type="citation_context",
                    page=page,
                    object_id=str(number),
                    locator_key="citation_id",
                    context=entry[:110],
                )
            )

    # 3. One text_span per page. Gold text_span items never carry an object id,
    #    so the page is the entire key and every page is a legal candidate.
    if include_text_spans:
        for index in range(1, text.n_pages + 1):
            head = re.sub(r"\s+", " ", text.pages[index - 1]).strip()[:110]
            add(
                EvidenceCandidate(
                    source_type="text_span",
                    page=index,
                    object_id="",
                    locator_key="",
                    context=head,
                )
            )

    return out


def format_candidates(candidates: list[EvidenceCandidate], limit: int = 220) -> str:
    """Numbered list for the reader prompt. The index is what the model returns."""
    lines = [f"{i}. {c.describe()}" for i, c in enumerate(candidates[:limit])]
    return "\n".join(lines) if lines else "(no locators could be read from this PDF)"
