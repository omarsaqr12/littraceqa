"""Local PDF reading: page text, caption indices, references, page rendering.

Two jobs:

* **Cross-checking the model's locator.** The evaluator's evidence key is
  ``(paper_id, source_type, page, object_id)``. A vision model that reads the
  right value can still misreport which page "Table 4" was on. Captions are
  regular enough in this corpus that a regex over page text gives an independent
  answer, and disagreement is a useful confidence signal.
* **Full-text search.** Content-defined `multi_paper` sets ("papers that mention
  MCTS in their method figure", "papers that cite UniAD in their main comparison
  table") cannot be answered from title+abstract at any k -- see
  reports/retrieval_findings.md. They need the body text.

Everything here is local and free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import pymupdf

#: "Table 4:", "Figure 2.", "Fig. 3", "Algorithm 1", "Equation (6)".
CAPTION = re.compile(
    r"^\s*(Table|Figure|Fig|Algorithm|Alg|Equation|Eq)\.?\s*([0-9]+[a-z]?)\s*[:.\)]?\s",
    re.I | re.M,
)
_CANONICAL = {
    "table": "Table", "figure": "Figure", "fig": "Figure",
    "algorithm": "Algorithm", "alg": "Algorithm",
    "equation": "Equation", "eq": "Equation",
}
_REFERENCES_HEAD = re.compile(r"^\s*(references|bibliography)\s*$", re.I | re.M)
#: "[24] Freda Shi, Mirac Suzgun, ..." or "24. Freda Shi, ..."
_REF_ENTRY = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})\.)\s+(.{15,})", re.M)


@dataclass(slots=True)
class Caption:
    kind: str          # "Table" | "Figure" | "Algorithm" | "Equation"
    number: str
    page: int
    object_id: str = ""

    def __post_init__(self) -> None:
        self.object_id = f"{self.kind} {self.number}"


@dataclass
class PaperText:
    paper_id: str
    path: Path
    pages: list[str] = field(default_factory=list)

    @property
    def n_pages(self) -> int:
        return len(self.pages)

    def full_text(self) -> str:
        return "\n".join(self.pages)

    @cached_property
    def captions(self) -> list[Caption]:
        found: list[Caption] = []
        for index, text in enumerate(self.pages, start=1):
            for match in CAPTION.finditer(text):
                kind = _CANONICAL[match.group(1).lower()]
                found.append(Caption(kind, match.group(2), index))
        return found

    def page_of(self, object_id: str) -> int | None:
        """First page carrying a caption for e.g. "Table 4". None if absent.

        Used to cross-check a model-reported page; a mismatch means one of the
        two is wrong and the evidence item deserves a lower confidence.
        """
        want = re.sub(r"\s+", " ", str(object_id or "")).strip().lower()
        for caption in self.captions:
            if caption.object_id.lower() == want:
                return caption.page
        return None

    def caption_text(self, object_id: str, chars: int = 400) -> str:
        page = self.page_of(object_id)
        if page is None:
            return ""
        text = self.pages[page - 1]
        want = str(object_id).split()
        pattern = re.compile(rf"{want[0]}\.?\s*{want[-1]}\b", re.I)
        match = pattern.search(text)
        return text[match.start(): match.start() + chars] if match else ""

    @cached_property
    def references(self) -> dict[int, str]:
        """Numbered reference list, ``{24: "Freda Shi, Mirac Suzgun, ..."}``.

        Enough for `citation_context` evidence, which the evaluator keys on the
        citation number alone -- no GROBID instance required.
        """
        text = self.full_text()
        heads = list(_REFERENCES_HEAD.finditer(text))
        if heads:
            text = text[heads[-1].end():]
        out: dict[int, str] = {}
        for match in _REF_ENTRY.finditer(text):
            number = int(match.group(1) or match.group(2))
            if number not in out:
                out[number] = re.sub(r"\s+", " ", match.group(3)).strip()[:600]
        return out

    def reference_page(self, number: int) -> int | None:
        marker = re.compile(rf"(\[{number}\]|^\s*{number}\.)\s+\S", re.M)
        for index, text in enumerate(self.pages, start=1):
            head = _REFERENCES_HEAD.search(text)
            window = text[head.end():] if head else text
            if index >= max(1, self.n_pages - 8) or head:
                if marker.search(window):
                    return index
        return None

    def search(self, pattern: str, *, flags: int = re.I) -> list[tuple[int, str]]:
        """Pages matching `pattern`, with a snippet. For full-text set questions."""
        compiled = re.compile(pattern, flags)
        hits = []
        for index, text in enumerate(self.pages, start=1):
            match = compiled.search(text)
            if match:
                start = max(0, match.start() - 120)
                hits.append((index, re.sub(r"\s+", " ", text[start: match.end() + 120])))
        return hits


def load_text(paper_id: str, path: Path) -> PaperText | None:
    try:
        with pymupdf.open(path) as document:
            pages = [page.get_text() for page in document]
    except Exception:
        return None
    return PaperText(paper_id=paper_id, path=path, pages=pages)


#: Ladder of (dpi, jpeg quality) tried by `shrink_pdf`, best first. 150 DPI
#: keeps body text and axis labels legible to a vision model.
_SHRINK_LADDER = ((150, 75), (120, 70), (100, 60), (80, 50))


def shrink_pdf(data: bytes, limit: int) -> bytes:
    """Rasterise a PDF down under `limit` bytes, or return it unchanged.

    Exists to keep every paper on the *inline* upload path. The Files API is the
    documented route for large attachments, but in practice it hung: a run froze
    with 100 threads and zero CPU growth, and a SIGALRM watchdog could not clear
    it because the block was inside SDK worker threads, not the main thread.

    Lossless recompression is useless here -- scientific PDFs are already
    image-compressed (39.8MB -> 39.0MB). Re-rendering pages as downsampled JPEGs
    is what actually works (39.8MB -> 9.45MB at 150 DPI). The cost is the text
    layer, so the model reads the page visually rather than extracting glyphs;
    for this task the page is being read visually regardless.
    """
    if len(data) <= limit:
        return data
    try:
        source = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return data
    try:
        for dpi, quality in _SHRINK_LADDER:
            out = pymupdf.open()
            try:
                for page in source:
                    image = page.get_pixmap(dpi=dpi).tobytes("jpeg", jpg_quality=quality)
                    new_page = out.new_page(width=page.rect.width, height=page.rect.height)
                    new_page.insert_image(page.rect, stream=image)
                candidate = out.tobytes(garbage=4, deflate=True)
            finally:
                out.close()
            if len(candidate) <= limit:
                return candidate
        return candidate  # smallest rung; caller decides what to do
    except Exception:
        return data
    finally:
        source.close()


def render_page(path: Path, page: int, zoom: float = 2.0) -> bytes | None:
    """PNG of one page, for the vision path (`localize.py` D2/D4)."""
    try:
        with pymupdf.open(path) as document:
            if not 1 <= page <= len(document):
                return None
            pixmap = document[page - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            return pixmap.tobytes("png")
    except Exception:
        return None
