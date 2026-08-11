"""Hybrid candidate generation: nickname + BM25 (+ optional dense), fused by RRF.

Design notes
------------
* **Per-mention retrieval, not per-question.** LitTraceQA questions routinely ask
  about two or three artefacts at once ("compare Trokens ... and the byte-pair
  visual encoder ..."). Scoring the whole question as one query buries the
  second paper. We run one retrieval per extracted mention and *union* the
  per-mention winners, which is what makes multi-paper recall move.
* **Reciprocal Rank Fusion** over the signal lists. RRF needs no score
  calibration between BM25 and cosine similarity, which matters because their
  scales are unrelated.
* **Soft scope.** Venue/year matches get a boost; out-of-scope papers survive.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from ..corpus import Paper, PaperPool
from .lexical import BM25Index, NicknameIndex, extract_nicknames
from .scope import Scope, extract_scope, scope_indices

RRF_K = 60.0


class DenseRetriever(Protocol):
    def search(
        self, query: str, top_k: int, candidates: set[int] | None = ...
    ) -> list[tuple[Paper, float]]: ...


@dataclass(slots=True)
class Candidate:
    paper: Paper
    score: float
    signals: dict[str, float] = field(default_factory=dict)
    mentions: set[str] = field(default_factory=set)


class HybridRetriever:
    """Union-of-mentions candidate generator over the paper pool."""

    def __init__(
        self,
        pool: PaperPool,
        bm25: BM25Index | None = None,
        nicknames: NicknameIndex | None = None,
        dense: DenseRetriever | None = None,
        *,
        scope_boost: float = 0.35,
        nickname_title_weight: float = 3.0,
        nickname_abstract_weight: float = 1.0,
    ):
        self.pool = pool
        self.bm25 = bm25 if bm25 is not None else BM25Index(pool)
        self.nicknames = nicknames if nicknames is not None else NicknameIndex(pool)
        self.dense = dense
        self.scope_boost = scope_boost
        self.nickname_title_weight = nickname_title_weight
        self.nickname_abstract_weight = nickname_abstract_weight

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _rrf(ranked_ids: list[str], weight: float = 1.0) -> dict[str, float]:
        return {pid: weight / (RRF_K + rank) for rank, pid in enumerate(ranked_ids, start=1)}

    def _accumulate(
        self,
        totals: dict[str, float],
        signals: dict[str, dict[str, float]],
        mentions: dict[str, set[str]],
        contribution: dict[str, float],
        name: str,
        mention: str | None,
    ) -> None:
        for pid, value in contribution.items():
            totals[pid] = totals.get(pid, 0.0) + value
            signals.setdefault(pid, defaultdict(float))[name] += value
            if mention:
                mentions.setdefault(pid, set()).add(mention)

    # -- public API -----------------------------------------------------------

    def retrieve(
        self,
        question: str,
        *,
        top_k: int = 40,
        per_mention_k: int = 12,
        question_level_k: int = 60,
        extra_mentions: list[str] | None = None,
        scope: Scope | None = None,
    ) -> list[Candidate]:
        scope = scope if scope is not None else extract_scope(question)
        in_scope = scope_indices(self.pool, scope)
        scope_ids = {self.pool.papers[i].paper_id for i in in_scope} if in_scope else set()

        mentions = list(dict.fromkeys((extra_mentions or []) + extract_nicknames(question)))

        totals: dict[str, float] = {}
        signals: dict[str, dict[str, float]] = {}
        mention_map: dict[str, set[str]] = {}

        # 1. Nickname lookup, per mention. Highest-precision signal.
        for mention in mentions:
            hits = self.nicknames.lookup(mention, restrict=in_scope)
            if not hits:  # fall back to pool-wide if the scope filter was wrong
                hits = self.nicknames.lookup(mention)
            title_hits = [p.paper_id for p, s in hits if s >= 1.0][:per_mention_k]
            abstract_hits = [p.paper_id for p, s in hits if s < 1.0][:per_mention_k]
            self._accumulate(totals, signals, mention_map,
                             self._rrf(title_hits, self.nickname_title_weight),
                             "nickname_title", mention)
            self._accumulate(totals, signals, mention_map,
                             self._rrf(abstract_hits, self.nickname_abstract_weight),
                             "nickname_abstract", mention)

        # 2. BM25, per mention and once for the whole question.
        for mention in mentions:
            ranked = [p.paper_id for p, _ in self.bm25.search(mention, per_mention_k, in_scope)]
            self._accumulate(totals, signals, mention_map, self._rrf(ranked, 1.0),
                             "bm25_mention", mention)
        ranked = [p.paper_id for p, _ in self.bm25.search(question, question_level_k, in_scope)]
        self._accumulate(totals, signals, mention_map, self._rrf(ranked, 1.5), "bm25_question", None)

        # 3. Dense, same shape as BM25 when a retriever is wired in.
        if self.dense is not None:
            for mention in mentions:
                ranked = [p.paper_id for p, _ in self.dense.search(mention, per_mention_k, in_scope)]
                self._accumulate(totals, signals, mention_map, self._rrf(ranked, 1.0),
                                 "dense_mention", mention)
            ranked = [p.paper_id for p, _ in self.dense.search(question, question_level_k, in_scope)]
            self._accumulate(totals, signals, mention_map, self._rrf(ranked, 1.5),
                             "dense_question", None)

        # 4. Soft scope boost.
        if scope_ids:
            for pid in list(totals):
                if pid in scope_ids:
                    bonus = self.scope_boost * totals[pid]
                    totals[pid] += bonus
                    signals.setdefault(pid, defaultdict(float))["scope"] += bonus

        candidates = [
            Candidate(self.pool[pid], score, dict(signals.get(pid, {})), mention_map.get(pid, set()))
            for pid, score in totals.items()
        ]
        candidates.sort(key=lambda c: -c.score)
        return candidates[:top_k]
