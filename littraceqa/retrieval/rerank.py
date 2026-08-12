"""Cross-encoder reranking of the candidate list.

`reports/retrieval_findings.md` isolates this as the binding constraint: every
selection policy lands near 0.40 paper F1 against a 0.756 oracle over the *same*
top-40 candidates. The gold papers are retrieved and then not picked, which is
precisely what a cross-encoder fixes -- it scores (query, document) jointly
instead of comparing two independently-built vectors.

Two scoring modes, because LitTraceQA questions are not single-intent:

* ``question`` -- one pass, ``(full question, title+abstract)``. Standard MS MARCO
  setup. Biases toward whichever artefact dominates the question's wording.
* ``per_mention`` -- one pass per named artefact, keeping each paper's best
  score. A question naming Trokens *and* a byte-pair visual encoder has two
  correct answers, and a single joint query buries the second.

Runs locally on the GPU, so it costs nothing per question and can be applied to
every candidate rather than a shortlist.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..corpus import Paper, PaperPool
from ..textnorm import clean

#: Strong general-purpose reranker. `bge-reranker-base` is ~3x faster with a
#: modest quality drop; `ms-marco-MiniLM-L-6-v2` is faster still.
DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"


@dataclass(slots=True)
class RerankedCandidate:
    paper: Paper
    score: float
    prior_rank: int
    best_mention: str = ""


class CrossEncoderReranker:
    def __init__(
        self,
        pool: PaperPool,
        model_name: str = DEFAULT_MODEL,
        *,
        device: str | None = None,
        batch_size: int = 64,
        max_abstract_chars: int = 900,
        #: Blend with the retriever's rank. Pure cross-encoder scores discard the
        #: lexical evidence that put a paper in the list at all, which on this
        #: task is often an exact artefact-name match -- the strongest signal we
        #: have. 0 = ignore prior rank, 1 = ignore the cross-encoder.
        prior_weight: float = 0.25,
    ):
        self.pool = pool
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_abstract_chars = max_abstract_chars
        self.prior_weight = prior_weight
        self._device = device
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=self._device)
        return self._model

    def _document(self, paper: Paper) -> str:
        return f"{clean(paper.title)}\n{clean(paper.abstract)[: self.max_abstract_chars]}"

    def rerank(
        self,
        question: str,
        candidates: list[str],
        *,
        mentions: list[str] | None = None,
        mode: str = "question",
        top_k: int | None = None,
    ) -> list[RerankedCandidate]:
        if not candidates:
            return []
        papers = [self.pool[pid] for pid in candidates if pid in self.pool.by_id]
        if not papers:
            return []
        documents = [self._document(p) for p in papers]
        prior = {p.paper_id: rank for rank, p in enumerate(papers)}

        queries: list[tuple[str, str]] = [("", question)]
        if mode == "per_mention" and mentions:
            queries = [(m, m) for m in mentions] + [("", question)]

        best: dict[str, tuple[float, str]] = {}
        for label, query in queries:
            pairs = [(query, document) for document in documents]
            scores = self.model.predict(
                pairs, batch_size=self.batch_size, show_progress_bar=False
            )
            for paper, score in zip(papers, scores):
                score = float(score)
                if paper.paper_id not in best or score > best[paper.paper_id][0]:
                    best[paper.paper_id] = (score, label)

        # Rank-based blend: comparable across models without score calibration.
        by_score = sorted(best.items(), key=lambda kv: -kv[1][0])
        fused: list[RerankedCandidate] = []
        for new_rank, (paper_id, (score, label)) in enumerate(by_score):
            old_rank = prior.get(paper_id, len(papers))
            blended = (1 - self.prior_weight) / (1 + new_rank) + \
                      self.prior_weight / (1 + old_rank)
            fused.append(
                RerankedCandidate(self.pool[paper_id], blended, old_rank, label)
            )
        fused.sort(key=lambda c: -c.score)
        return fused[:top_k] if top_k else fused
