"""Acronym-of-title matching.

Questions refer to papers by the acronym the community uses, which is frequently
built from the title's initials and appears nowhere in the metadata text:

    "IMM"  -> "Inductive Moment Matching"        (icml2025_01371)
    "TCM"  -> "Truncated Consistency Models"     (iclr2025_03463)
    "MoD"  -> "Mixture of Decoding: ..."         (acl2025_01863)

Neither BM25 nor substring lookup can bridge that gap, and on the validation set
these are exactly the papers every other signal misses. The index enumerates a
handful of plausible initialisms per title and looks them up by exact match --
cheap, and precise enough that a hit is nearly always correct.

This is the retrieval-side analogue of Schwartz-Hearst abbreviation extraction,
applied in reverse: instead of finding "(IMM)" next to its expansion in running
text, we generate the candidate abbreviations a title could plausibly produce.
"""

from __future__ import annotations

from collections import defaultdict

from ..corpus import Paper, PaperPool
from ..textnorm import clean, squash

#: Function words that an acronym may either keep ("MoD") or drop ("MD").
_FUNCTION_WORDS = {
    "a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with", "via",
    "from", "by", "at", "as", "is", "are", "into", "through", "over", "under",
}

#: Trailing subtitle markers -- acronyms are almost always built from the part
#: before the colon ("Mixture of Decoding: An Attention-Inspired ...").
_SUBTITLE_SPLITTERS = (":", " - ", " -- ", "?", "!")


def _head(title: str) -> str:
    """The part of a title an acronym is plausibly built from."""
    text = clean(title)
    for splitter in _SUBTITLE_SPLITTERS:
        index = text.find(splitter)
        if index > 0:
            text = text[:index]
            break
    return text


def title_acronyms(title: str, max_words: int = 8) -> set[str]:
    """Plausible squashed initialisms for a title.

    Generates, over the pre-subtitle head:
      * initials of every word            ("Mixture of Decoding" -> "mod")
      * initials of content words only    ("Mixture of Decoding" -> "md")
      * both of the above for every prefix of the head, so that acronyms drawn
        from the first N words still match ("Truncated Consistency Models
        Are Great" -> "tcm")
    """
    words = [w for w in _head(title).split() if any(ch.isalnum() for ch in w)]
    if not words or len(words) > max_words * 3:
        return set()
    words = words[:max_words]

    out: set[str] = set()
    for end in range(2, len(words) + 1):
        window = words[:end]
        all_initials = squash("".join(w[0] for w in window))
        content = [w for w in window if w.lower() not in _FUNCTION_WORDS]
        content_initials = squash("".join(w[0] for w in content))
        for candidate in (all_initials, content_initials):
            if 2 <= len(candidate) <= 8:
                out.add(candidate)
    return out


class AcronymIndex:
    """Exact lookup from a squashed acronym to the papers whose title yields it."""

    #: An acronym mapping to more papers than this is not discriminative.
    MAX_POSTINGS = 60

    def __init__(self, pool: PaperPool):
        self.pool = pool
        buckets: dict[str, list[int]] = defaultdict(list)
        for index, paper in enumerate(pool.papers):
            for acronym in title_acronyms(paper.title):
                buckets[acronym].append(index)
        self.buckets = {k: v for k, v in buckets.items() if len(v) <= self.MAX_POSTINGS}

    def lookup(
        self, nickname: str, restrict: set[int] | None = None, limit: int = 20
    ) -> list[tuple[Paper, float]]:
        key = squash(nickname)
        if len(key) < 2:
            return []
        indices = self.buckets.get(key, ())
        hits = [i for i in indices if restrict is None or i in restrict]
        if not hits and restrict is not None:  # scope parse may have been wrong
            hits = list(indices)
        # Rarer acronyms are stronger evidence.
        weight = 1.0 / (1.0 + 0.15 * max(len(indices) - 1, 0))
        return [(self.pool.papers[i], weight) for i in hits[:limit]]
