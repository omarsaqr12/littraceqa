"""Drop selected papers that never mention what the question asks about.

Paper precision on test is 0.817, so roughly one paper in five that we return is
wrong. Precision is the half worth attacking: recall is already 0.799 and nearly
balanced with precision, so adding papers no longer pays, while removing wrong
ones is free score.

The test is nearly false-positive-free. A question about `IMM` is about a paper
that says "IMM" repeatedly; a candidate whose full text never contains the string
is not that paper. Unlike title or abstract similarity this looks at the whole
document, so it is unaffected by an artefact being introduced in section 4 and
absent from the abstract -- which is exactly the case retrieval keeps getting
wrong.

Why it is worth more than its own component: evidence recall is bounded by
`paper_recall x locator_accuracy`, and multiple-choice accuracy collapses when the
paper is wrong (0.600 with a correct paper, 0.062 without). Paper selection
multiplies into two thirds of the score beyond its own third.

Uses only cached PDFs -- no API calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..corpus import Paper, PaperPool
from ..pdf.read import load_text
from ..textnorm import squash


@dataclass(slots=True)
class MentionEvidence:
    paper_id: str
    hits: int
    matched: list[str]
    checked: bool = True


class MentionVerifier:
    """Count question-mention occurrences in each candidate's full text."""

    #: Shorter strings match inside unrelated words even after squashing.
    MIN_MENTION = 4
    #: A paper is only dropped when some *other* candidate clears this, so a
    #: question whose mentions appear nowhere leaves the set untouched.
    MIN_HITS = 2

    def __init__(self, pool: PaperPool, fetcher, *, max_papers_checked: int = 6):
        self.pool = pool
        self.fetcher = fetcher
        self.max_papers_checked = max_papers_checked
        self._cache: dict[str, str] = {}

    def _squashed_text(self, paper: Paper) -> str | None:
        if paper.paper_id in self._cache:
            return self._cache[paper.paper_id] or None
        result = self.fetcher.fetch(paper)
        if not result.ok:
            self._cache[paper.paper_id] = ""
            return None
        text = load_text(paper.paper_id, result.path)
        squashed = squash(text.full_text()) if text is not None else ""
        self._cache[paper.paper_id] = squashed
        return squashed or None

    def score(self, paper: Paper, mentions: list[str]) -> MentionEvidence:
        body = self._squashed_text(paper)
        if body is None:
            # No PDF is not evidence of absence; never drop on a fetch failure.
            return MentionEvidence(paper.paper_id, 0, [], checked=False)
        hits = 0
        matched: list[str] = []
        for mention in mentions:
            key = squash(mention)
            if len(key) < self.MIN_MENTION:
                continue
            count = body.count(key)
            if count:
                hits += count
                matched.append(mention)
        return MentionEvidence(paper.paper_id, hits, matched)

    def filter(
        self, paper_ids: list[str], mentions: list[str], *, keep_min: int = 1
    ) -> tuple[list[str], list[MentionEvidence]]:
        """Drop candidates with no mention support, when others have it.

        Conservative by construction: the set is only reduced when at least one
        paper clears `MIN_HITS`, and never below `keep_min`. Order is preserved,
        so the ranker's opinion still decides among survivors.
        """
        usable = [m for m in mentions if len(squash(m)) >= self.MIN_MENTION]
        if not usable or len(paper_ids) <= keep_min:
            return paper_ids, []

        scored = [
            self.score(self.pool[p], usable)
            for p in paper_ids[: self.max_papers_checked]
            if p in self.pool.by_id
        ]
        by_id = {s.paper_id: s for s in scored}
        supported = [s for s in scored if s.checked and s.hits >= self.MIN_HITS]
        if not supported:
            return paper_ids, scored  # nothing to compare against; change nothing

        kept = [
            p for p in paper_ids
            if p not in by_id                      # unchecked (beyond the cap)
            or not by_id[p].checked                # no PDF
            or by_id[p].hits >= self.MIN_HITS
        ]
        if len(kept) < keep_min:
            return paper_ids, scored
        return kept, scored
