"""End-to-end pipeline, assembled from swappable stage implementations.

Stage boundaries match plan.md §4 so the ablation harness can vary one stage at
a time:

    A mentions/scope -> B candidates -> C rank+expand -> D read PDFs -> E synthesise

Everything before D is local and free; D is the only stage that spends API quota,
and it is bounded by `max_papers_to_read` per question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .answer.build import build_record
from .corpus import Paper, PaperPool, Question
from .pdf.fetch import PDFFetcher
from .reason.client import GeminiClient
from .reason.localize import PaperReader, Reading
from .reason.solve import AnswerSolver
from .retrieval.acronym import AcronymIndex
from .retrieval.dense import DenseRetriever
from .retrieval.expand import ClusterExpander, predict_set_size
from .retrieval.hybrid import HybridRetriever
from .retrieval.lexical import BM25Index, NicknameIndex, extract_nicknames
from .retrieval.scope import extract_scope


@dataclass
class PipelineConfig:
    # -- stage B/C
    candidate_k: int = 40
    use_dense: bool = True
    use_acronyms: bool = True
    #: Expand the paper set along the embedding graph (plan.md §2.2). The single
    #: biggest lever on paper F1; ~0.6 F1 on multi_paper questions.
    use_expansion: bool = True
    expansion_similarity: float = 0.86
    max_set_size: int = 6
    #: Fallback size when the question gives no usable count cue.
    default_set_size: int = 1

    # -- stage D
    max_papers_to_read: int = 3
    read_confidence_floor: float = 0.35
    #: Emit evidence only from papers we actually read and believe.
    evidence_confidence_floor: float = 0.45

    # -- stage E
    mc_samples: int = 3


@dataclass
class QuestionTrace:
    """Everything a stage produced, for debugging and per-stage ablation."""
    query_id: str
    mentions: list[str] = field(default_factory=list)
    scope: Any = None
    candidates: list[str] = field(default_factory=list)
    seeds: list[str] = field(default_factory=list)
    predicted_size: int = 1
    size_reason: str = ""
    paper_ids: list[str] = field(default_factory=list)
    readings: list[Reading] = field(default_factory=list)
    fetch_failures: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        pool: PaperPool,
        *,
        config: PipelineConfig | None = None,
        client: GeminiClient | None = None,
        fetcher: PDFFetcher | None = None,
        dense: DenseRetriever | None = None,
    ):
        self.pool = pool
        self.config = config or PipelineConfig()
        self.client = client
        self.fetcher = fetcher or PDFFetcher()

        self.bm25 = BM25Index(pool)
        self.nicknames = NicknameIndex(pool)
        self.acronyms = AcronymIndex(pool) if self.config.use_acronyms else None
        self.dense = dense
        if self.config.use_dense and self.dense is None:
            self.dense = DenseRetriever(pool)
            self.dense.build(show_progress=False)
        self.retriever = HybridRetriever(pool, self.bm25, self.nicknames, dense=self.dense)
        self.expander = (
            ClusterExpander(pool, self.dense, min_similarity=self.config.expansion_similarity)
            if self.config.use_expansion and self.dense is not None
            else None
        )
        self.reader = PaperReader(client) if client is not None else None
        self.solver = AnswerSolver(client, mc_samples=self.config.mc_samples) if client else None

    # -- stages A-C: paper selection (local, free) -----------------------------

    def select_papers(self, question: Question) -> QuestionTrace:
        cfg = self.config
        trace = QuestionTrace(query_id=question.query_id)
        trace.mentions = extract_nicknames(question.question)
        trace.scope = extract_scope(question.question)

        candidates = self.retriever.retrieve(
            question.question,
            top_k=cfg.candidate_k,
            extra_mentions=trace.mentions,
            scope=trace.scope,
        )
        ranked = [c.paper.paper_id for c in candidates]

        # Acronym hits are high precision but arrive unranked; lift them near the
        # top rather than appending, or RRF mass from noisier signals buries them.
        if self.acronyms is not None:
            acronym_hits: list[str] = []
            for mention in trace.mentions:
                for paper, _ in self.acronyms.lookup(mention, limit=4):
                    if paper.paper_id not in acronym_hits:
                        acronym_hits.append(paper.paper_id)
            for paper_id in reversed(acronym_hits[:4]):
                if paper_id in ranked:
                    ranked.remove(paper_id)
                ranked.insert(min(3, len(ranked)), paper_id)

        trace.candidates = ranked

        prediction = predict_set_size(
            question.question, single_default=cfg.default_set_size
        )
        size = max(1, min(prediction.size, cfg.max_set_size))
        trace.predicted_size = size
        trace.size_reason = prediction.reason

        seeds = ranked[: max(1, min(size, len(ranked)))]
        trace.seeds = seeds

        if self.expander is not None and not prediction.confident:
            trace.paper_ids = self.expander.expand(
                seeds[:1] if size == 1 else seeds,
                target_size=size,
                scope=trace.scope,
                allowed=ranked,
            )
        else:
            trace.paper_ids = seeds
        return trace

    # -- stage D: read the PDFs ------------------------------------------------

    def read_papers(self, question: Question, trace: QuestionTrace) -> list[Reading]:
        if self.reader is None:
            return []
        readings: list[Reading] = []
        for paper_id in trace.paper_ids[: self.config.max_papers_to_read]:
            paper: Paper = self.pool[paper_id]
            result = self.fetcher.fetch(paper)
            if not result.ok:
                trace.fetch_failures.append(paper_id)
                continue
            readings.append(
                self.reader.read(
                    question, paper, result.path, trust_pages=result.pagination_trusted
                )
            )
        return readings

    # -- stage E: synthesise ---------------------------------------------------

    def build_answer(
        self, question: Question, trace: QuestionTrace, readings: list[Reading]
    ) -> dict[str, Any]:
        titles = {pid: self.pool[pid].title for pid in trace.paper_ids if pid in self.pool.by_id}
        papers = [self.pool[pid] for pid in trace.paper_ids if pid in self.pool.by_id]
        parts: dict[str, Any] = {}
        if self.solver is None:
            return parts
        if "multiple_choice" in question.answer_types:
            parts["multiple_choice"] = self.solver.solve_multiple_choice(
                question, readings, titles
            )
        if "table" in question.answer_types:
            parts["table"] = self.solver.solve_table(question, readings, titles, papers)
        if "freeform" in question.answer_types:
            parts["freeform"] = self.solver.solve_freeform(question, readings, titles)
        return parts

    def collect_evidence(self, readings: list[Reading]) -> list[dict[str, Any]]:
        """Evidence from readings we believe.

        Evidence F1 is macro-averaged and gold sets are small (1-4 items), so a
        speculative extra item costs real precision. Only papers where the model
        said it found the answer, above the confidence floor, contribute.
        """
        floor = self.config.evidence_confidence_floor
        out: list[dict[str, Any]] = []
        for reading in readings:
            if reading.found and reading.confidence >= floor:
                out.extend(reading.to_evidence_records())
        return out

    # -- full run --------------------------------------------------------------

    def run_question(self, question: Question) -> tuple[dict[str, Any], QuestionTrace]:
        trace = self.select_papers(question)
        readings = self.read_papers(question, trace)
        trace.readings = readings
        record = build_record(
            question,
            trace.paper_ids,
            self.collect_evidence(readings),
            self.build_answer(question, trace, readings),
        )
        return record, trace
