"""Cluster expansion -- recovering the sibling papers a `multi_paper` question grades.

Why this exists
---------------
`multi_paper` gold sets are not "the papers containing the answer". They are the
topical comparison set the question was drawn from. On validation, 6 of 29
`multi_paper` questions place all their evidence in **one** paper while gold lists
**four**, and one 4-paper cluster is shared verbatim by 12 different questions.

Scoring consequence, for a 4-paper gold set:

    return the answer paper only   ->  P=1.00  R=0.25  F1=0.40
    return the right 4             ->  P=1.00  R=1.00  F1=1.00

So expansion is worth ~0.6 macro F1 on the ~half of questions that are
`multi_paper`. This is entity set expansion (Google Sets / SEISA lineage), not
retrieval: seed with what we are confident about, then grow along the similarity
graph while the set stays coherent.

The risk is symmetric -- expanding a genuinely single-paper question from 1 to 4
drops it from F1 1.00 to 0.40 -- so `predict_set_size` is the safety valve and
should be tuned against `paper_f1_macro` directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..corpus import Paper, PaperPool
from .dense import DenseRetriever
from .scope import Scope, scope_indices

#: Observed gold-set sizes on validation: 26x1, 1x3, 27x4, 1x9.
DEFAULT_SINGLE_SIZE = 1
DEFAULT_MULTI_SIZE = 4

_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}

#: A count only tells us the gold-set size when it governs a *paper* noun.
#: "the two prompt compression methods" is about table rows, not papers -- a bare
#: count-word regex scores 0/3 on validation for exactly this reason.
_PAPER_NOUNS = r"(?:papers?|works?|studies|publications?|submissions?)"
_COUNT_BEFORE = re.compile(
    r"\b(" + "|".join(_NUMBER_WORDS) + r"|both)\b"
    r"(?:\s+\w+){0,4}?\s+" + _PAPER_NOUNS + r"\b",
    re.I,
)

#: Phrasings that ask for an open-ended set ("which CVPR 2025 papers ...").
_OPEN_SET = re.compile(
    r"\b(?:which|what|list|identify|all|any)\b(?:\s+\w+){0,6}?\s+" + _PAPER_NOUNS,
    re.I,
)

#: Phrasings that pin the question to exactly one paper.
_SINGLE_MARKERS = re.compile(
    r"\b(?:in|from|of)\s+the\s+[\w.\-]+\s+(?:paper|work|study)\b|"
    r"\bthe\s+(?:same|single|one)\s+paper\b",
    re.I,
)


@dataclass(slots=True)
class SetSizePrediction:
    size: int
    reason: str
    confident: bool


def predict_set_size(
    question: str,
    *,
    n_mentions: int = 0,
    single_default: int = DEFAULT_SINGLE_SIZE,
    multi_default: int = DEFAULT_MULTI_SIZE,
) -> SetSizePrediction:
    """How many papers to return.

    Only two surface cues survived validation: an explicit count governing a
    paper noun ("the **two** ICCV 2025 papers"), and an open-set phrasing
    ("**which** CVPR 2025 papers ..."). Everything else defaults.

    Two heuristics that look sensible and are *not* used, because they were
    measured and are actively harmful:

    * "names a single paper" -> size 1. Fires on "In the TCM paper, ...", whose
      gold set is the 4-paper consistency-model cluster. Wrong on 6 of 55.
    * "n distinct artefacts named" -> size n. Fires on questions that name
      several *methods compared inside one table* ("500xCompressor outperform
      ICAE"), whose gold is a single paper. Wrong on 10 of 55.

    Together those two rules dropped exact-size accuracy to 40%. Gold set size is
    largely a property of how the benchmark was annotated -- whether a comparison
    cluster was built around the paper -- and is barely visible in the question.
    Do not chase it with more regexes; pick the size that maximises expected F1
    instead (`exp/04_set_size_sweep.py`, and `min_similarity` for adaptive stopping).
    """
    match = _COUNT_BEFORE.search(question)
    if match:
        word = match.group(1).lower()
        size = 2 if word == "both" else _NUMBER_WORDS[word]
        return SetSizePrediction(size, f"explicit count {word!r} governing a paper noun", True)

    if _OPEN_SET.search(question):
        return SetSizePrediction(multi_default, "open-ended set question", False)

    return SetSizePrediction(single_default, "default", False)


class ClusterExpander:
    def __init__(
        self,
        pool: PaperPool,
        dense: DenseRetriever,
        *,
        min_similarity: float = 0.72,
        neighbour_pool: int = 60,
    ):
        self.pool = pool
        self.dense = dense
        self.min_similarity = min_similarity
        self.neighbour_pool = neighbour_pool

    def expand(
        self,
        seeds: list[str],
        target_size: int,
        *,
        scope: Scope | None = None,
        allowed: list[str] | None = None,
    ) -> list[str]:
        """Grow `seeds` to `target_size` paper ids along the similarity graph.

        `allowed` (typically the reranked candidate list) is preferred over raw
        nearest neighbours when supplied: a paper that both the retriever and the
        embedding graph like is a better bet than one only the graph likes.
        """
        chosen = list(dict.fromkeys(seeds))[:target_size]
        if len(chosen) >= target_size:
            return chosen

        restrict = scope_indices(self.pool, scope) if scope is not None else None

        # 1. Prefer already-retrieved candidates, ordered by similarity to seeds.
        if allowed:
            remaining = [pid for pid in allowed if pid not in chosen]
            if remaining:
                ranked = self.dense.neighbours(
                    chosen,
                    top_k=len(self.pool),
                    candidates={self.pool.order[p] for p in remaining if p in self.pool.order},
                )
                for paper, score in ranked:
                    if len(chosen) >= target_size:
                        break
                    if score >= self.min_similarity:
                        chosen.append(paper.paper_id)

        # 2. Fall back to pool-wide neighbours.
        if len(chosen) < target_size:
            for paper, score in self.dense.neighbours(
                chosen, top_k=self.neighbour_pool, candidates=restrict
            ):
                if len(chosen) >= target_size:
                    break
                if paper.paper_id not in chosen and score >= self.min_similarity:
                    chosen.append(paper.paper_id)

        return chosen[:target_size]
