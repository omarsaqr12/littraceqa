"""Venue/year scope extraction from question text.

24 of the 71 test questions state a venue ("these ICCV 2025 papers"), and the
paper pool is partitioned cleanly by venue -- ICCV 2025 is 2,701 of 27,487 papers.
Applying the filter shrinks the candidate space ~10x at essentially zero recall
cost, which lifts precision on every downstream stage.

Scope is applied as a *soft* filter: in-scope papers are boosted rather than
non-scope papers dropped, because a question can name a venue for one of its
papers while a second paper comes from elsewhere ("Across all venues, ...").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..corpus import PaperPool

VENUE_PATTERNS = {
    "ACL": r"\bACL\b",
    "NAACL": r"\bNAACL\b",
    "EMNLP": r"\bEMNLP\b",
    "CVPR": r"\bCVPR\b",
    "ICCV": r"\bICCV\b",
    "ECCV": r"\bECCV\b",
    "ICLR": r"\bICLR\b",
    "ICML": r"\bICML\b",
    "NeurIPS": r"\bNeurIPS\b|\bNIPS\b|\bNeural\s+Information\s+Processing\b",
}

_YEAR = re.compile(r"\b(20(?:2[0-9]))\b")
_ALL_VENUES = re.compile(r"across\s+all\s+venues|any\s+venue|regardless\s+of\s+venue", re.I)


@dataclass(slots=True)
class Scope:
    venues: list[str]
    years: list[int]
    explicit_all_venues: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.venues and not self.years


def extract_scope(question: str) -> Scope:
    venues = [v for v, pattern in VENUE_PATTERNS.items() if re.search(pattern, question, re.I)]
    years = sorted({int(y) for y in _YEAR.findall(question)})
    return Scope(venues, years, bool(_ALL_VENUES.search(question)))


def scope_indices(pool: PaperPool, scope: Scope) -> set[int] | None:
    """Row indices of papers matching `scope`, or None when the scope is unusable.

    Returns None (meaning "no restriction") when the scope is empty, says
    "across all venues", or would match nothing -- never let a bad parse
    zero out the candidate set.
    """
    if scope.is_empty or scope.explicit_all_venues:
        return None
    venues = {v.lower() for v in scope.venues}
    years = set(scope.years)
    keep = {
        index
        for index, paper in enumerate(pool.papers)
        if (not venues or paper.venue.lower() in venues)
        and (not years or paper.year in years)
    }
    return keep or None
