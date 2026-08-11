"""Loading of the LitTraceQA inputs, gold labels, and the 27,487-paper pool."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .textnorm import clean, squash, tokens

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

VENUES = ["ACL", "CVPR", "ECCV", "EMNLP", "ICCV", "ICLR", "ICML", "NAACL", "NeurIPS"]


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(rows: list[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


@dataclass(slots=True)
class Paper:
    paper_id: str
    title: str
    abstract: str
    authors: list[str]
    venue: str
    year: int
    track: str
    pdf_url: str
    source_url: str
    openreview_id: str | None
    anthology_id: str | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    # Derived, cached at load time -- every retriever needs them.
    title_clean: str = ""
    title_squashed: str = ""
    text_squashed: str = field(repr=False, default="")
    doc_tokens: list[str] = field(repr=False, default_factory=list)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Paper":
        title = record.get("title") or ""
        abstract = record.get("abstract") or ""
        paper = cls(
            paper_id=record["paper_id"],
            title=title,
            abstract=abstract,
            authors=record.get("authors") or [],
            venue=record.get("venue") or "",
            year=int(record.get("year") or 0),
            track=record.get("track") or "",
            pdf_url=record.get("pdf_url") or "",
            source_url=record.get("source_url") or "",
            openreview_id=record.get("openreview_id"),
            anthology_id=record.get("anthology_id"),
            raw=record,
        )
        paper.title_clean = clean(title)
        paper.title_squashed = squash(title)
        paper.text_squashed = squash(f"{title} {abstract}")
        paper.doc_tokens = tokens(f"{title} {title} {abstract}")  # title double-weighted
        return paper


@dataclass(slots=True)
class Question:
    query_id: str
    question: str
    answer_types: list[str]
    multiple_choice_options: dict[str, str] | None = None
    table_schema: list[dict[str, Any]] | None = None
    benchmark: str = "LitTraceQA"
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Question":
        options = record.get("multiple_choice_options")
        if isinstance(options, list):  # [{"label": "A", "text": "..."}, ...]
            options = {
                str(option.get("label")): str(option.get("text"))
                for option in options
                if isinstance(option, dict)
            }
        elif isinstance(options, dict):
            options = {str(k): str(v) for k, v in options.items()}
        return cls(
            query_id=record["query_id"],
            question=record.get("question") or "",
            answer_types=list(record.get("answer_types") or []),
            multiple_choice_options=options,
            table_schema=record.get("table_schema"),
            benchmark=record.get("benchmark") or "LitTraceQA",
            raw=record,
        )


class PaperPool:
    """In-memory index over ``paper_metadata.jsonl``."""

    def __init__(self, papers: list[Paper]):
        self.papers = papers
        self.by_id: dict[str, Paper] = {p.paper_id: p for p in papers}
        self.order: dict[str, int] = {p.paper_id: i for i, p in enumerate(papers)}

    @classmethod
    def load(cls, path: str | Path = DATA_DIR / "paper_metadata.jsonl") -> "PaperPool":
        return cls([Paper.from_record(r) for r in read_jsonl(path)])

    def __len__(self) -> int:
        return len(self.papers)

    def __iter__(self) -> Iterator[Paper]:
        return iter(self.papers)

    def __getitem__(self, paper_id: str) -> Paper:
        return self.by_id[paper_id]

    def subset(self, venue: str | None = None, year: int | None = None) -> list[Paper]:
        return [
            p for p in self.papers
            if (venue is None or p.venue.lower() == venue.lower())
            and (year is None or p.year == year)
        ]


def load_questions(path: str | Path) -> list[Question]:
    return [Question.from_record(r) for r in read_jsonl(path)]


def load_gold(path: str | Path = DATA_DIR / "validation.jsonl") -> dict[str, dict[str, Any]]:
    return {r["query_id"]: r for r in read_jsonl(path)}
