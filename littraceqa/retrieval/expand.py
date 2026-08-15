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
from typing import TYPE_CHECKING

from ..corpus import Paper, PaperPool
from .scope import Scope, scope_indices

if TYPE_CHECKING:  # `predict_set_size` is pure regex -- importing it must not
    from .dense import DenseRetriever  # drag in numpy/torch via the dense stack.

#: Observed gold-set sizes on validation: 26x1, 1x3, 27x4, 1x9.
DEFAULT_SINGLE_SIZE = 1
DEFAULT_MULTI_SIZE = 4

_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}

#: A word of a noun phrase. Must include hyphens, dashes and slashes: ML papers
#: are described almost entirely in hyphenated compounds ("alignment-related",
#: "detection-acceleration/annotation"), and a bare `\w+` splits each of those
#: into two tokens. That silently blew the intervening-word budget below and made
#: "the two ICCV 2025 alignment-related adversarial papers" -- an explicit,
#: confident count -- read as a single-paper question. On the test split the
#: fix takes explicit-count detections from 10 to 20 of 71.
_NP_WORD = r"[\w–—/-]+"

#: A count only tells us the gold-set size when it governs a *paper* noun.
#: "the two prompt compression methods" is about table rows, not papers -- a bare
#: count-word regex scores 0/3 on validation for exactly this reason.
_PAPER_NOUNS = r"(?:papers?|works?|studies|publications?|submissions?)"
_COUNT_BEFORE = re.compile(
    r"\b(" + "|".join(_NUMBER_WORDS) + r"|both)\b"
    r"(?:\s+" + _NP_WORD + r"){0,6}?\s+" + _PAPER_NOUNS + r"\b",
    re.I,
)

#: Phrasings that ask for an open-ended set ("which CVPR 2025 papers ...").
#: **Plural only.** "Across all venues, which VLM-based driving *paper* achieves
#: the highest driving score" is a single-paper question that the singular-
#: tolerant `papers?` used to read as an open set, returning 4 papers for a
#: 1-paper gold set (q_021: F1 1.00 -> 0.40).
_PLURAL_PAPER_NOUNS = r"(?:papers|works|studies|publications|submissions)"
_OPEN_SET = re.compile(
    r"\b(?:which|what|list|identify|all|any)\b(?:\s+" + _NP_WORD + r"){0,6}?\s+"
    + _PLURAL_PAPER_NOUNS + r"\b",
    re.I,
)

#: A plural paper noun under a determiner, with no count attached: "Across these
#: ICCV 2025 efficiency papers", "Among these motion-focused papers". The
#: question is explicitly about more than one paper even though it never says
#: how many.
_PLURAL_SET = re.compile(
    r"\b(?:these|those|across|among|between|both)\b(?:\s+" + _NP_WORD + r"){0,6}?\s+"
    r"(?:papers|works|studies|publications|submissions)\b",
    re.I,
)

#: "the encoder-free VLM paper ... and the object-detector event-understanding
#: paper ...". Each match is one paper referred to by description rather than by
#: name, so the number of matches is the number of papers.
_DESCRIBED_PAPER = re.compile(
    r"\bthe\s+(?:" + _NP_WORD + r"\s+){0,8}?(?:paper|work|study)\b",
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

    # Two weaker cues, both of which say "more than one paper" without saying how
    # many. They are worth acting on because the cost is asymmetric: on a
    # 2-paper gold set, returning 1 paper caps F1 at 0.67, while returning 2 when
    # gold is 1 drops it to 0.67 as well -- but the test split is the named-paper
    # regime (reports/leaderboard_gap.md), where the plural is usually literal.
    # Both stay `confident=False` so a caller can gate on that.
    described = len(_DESCRIBED_PAPER.findall(question))
    if described >= 2:
        return SetSizePrediction(
            min(described, multi_default), f"{described} papers referred to by description", False
        )

    if _PLURAL_SET.search(question):
        return SetSizePrediction(2, "plural paper noun with no count", False)

    return SetSizePrediction(single_default, "default", False)


class ClusterExpander:
    def __init__(
        self,
        pool: PaperPool,
        dense: "DenseRetriever",
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
