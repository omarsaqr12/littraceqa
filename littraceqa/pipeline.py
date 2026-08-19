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
from .answer.table_visual import VisualTableSolver
from .corpus import Paper, PaperPool, Question
from .pdf.fetch import PDFFetcher
from .pdf.objects import objects_in_pdf
from .reason.client import GeminiClient
from .reason.localize import PaperReader, Reading
from .reason.solve import AnswerSolver
from .retrieval.acronym import AcronymIndex
from .retrieval.dense import DenseRetriever
from .retrieval.expand import ClusterExpander, predict_set_size
from .retrieval.hybrid import HybridRetriever
from .retrieval.lexical import BM25Index, NicknameIndex, extract_nicknames
from .retrieval.scope import extract_scope
from .retrieval.rerank import CrossEncoderReranker
from .retrieval.select import MentionAnchoredSelector
from .retrieval.verify import LLMPaperSelector


@dataclass
class PipelineConfig:
    # -- stage B/C
    #: "fused" wins on validation's cluster regime; "mention_anchored" targets
    #: the named-paper regime the test split almost certainly uses. See
    #: retrieval/select.py and reports/retrieval_findings.md.
    selection: str = "fused"
    candidate_k: int = 40
    #: Cross-encoder rerank of the candidate list. MEASURED WIN (exp/08):
    #: paper F1 0.410 -> 0.490, and single-paper 0.692 -> 0.846, which is the
    #: family the test regime resembles. Local and free; ~25s/question on CPU.
    use_reranker: bool = True
    #: "question" scores (full question, title+abstract). Do NOT use
    #: "per_mention": measured at 0.396, *below* the 0.410 baseline -- a bare
    #: artefact name gives the cross-encoder too little context.
    rerank_mode: str = "question"
    rerank_prior_weight: float = 0.5
    #: LLM picks the final paper set out of the reranked shortlist. MEASURED WIN
    #: (exp/13): validation paper F1 0.4901 -> 0.5837, precision 0.614 -> 0.758.
    #: Recognition, not recall -- asking the same model to *generate* the title
    #: instead (exp/12) scored 0.2170, because it invents plausible titles around
    #: artefact names it does know. One call per question, titles+abstracts only.
    use_llm_selector: bool = False
    llm_shortlist: int = 20
    #: Independent selector passes, majority-voted. Selection is the binding
    #: constraint on paper F1 (86% of what the shortlist permits), so this is
    #: the cheapest remaining accuracy on the heaviest component.
    llm_select_samples: int = 1
    #: Model for the selector step only. None keeps the client's chain.
    llm_select_model: str | None = None
    #: Read table CELLS off a rendered page instead of out of the evidence
    #: digest. Row keys stay with the existing logic: exp/14 measured that
    #: letting the image choose rows too moved row F1 0.5280 -> 0.4591 while
    #: cell accuracy went 0.0682 -> 0.1591, and the row losses were entirely
    #: questions the paper-title path already handles (q_027 1.00 -> 0.00).
    #: Cells and row keys are separable; only cells benefit from the picture.
    visual_table_cells: bool = False
    #: Put a paper that a mention matches *uniquely* by title n-gram at rank 0,
    #: after reranking. MEASURED AND DISABLED: paper F1 0.490 -> 0.465 overall,
    #: and it loses on the test-like family too (0.846 -> 0.808), which is where
    #: the idea should have paid off. The premise was sound -- q_004's "DynaPipe"
    #: matches exactly one of 27,487 titles at score 1.0 and still lost its slot
    #: -- but `extract_nicknames` yields every named artefact in the question,
    #: and most of them are datasets, baselines or metrics rather than the paper
    #: being asked about. Pinning "NaturalQ" or "ICAE" evicts the right paper
    #: more often than pinning "DynaPipe" recovers it. Kept as a flag so the
    #: claim can be re-measured if mention extraction ever learns which mention
    #: names the *subject* of the question. See `Pipeline._exact_title_matches`.
    pin_exact_title_matches: bool = False
    use_dense: bool = True
    use_acronyms: bool = True
    #: Expand the paper set along the embedding graph. MEASURED AND DISABLED:
    #: seeding kNN with a gold paper recovers only 20% of its cluster siblings at
    #: k=3 (exp/06). The clusters are defined by full-text properties, not
    #: abstract-level similarity. See reports/retrieval_findings.md.
    use_expansion: bool = False
    expansion_similarity: float = 0.86
    max_set_size: int = 6
    #: Fallback size when the question gives no usable count cue.
    default_set_size: int = 1

    # -- stage D
    #: Enumerate candidate locators from the PDF and have the reader pick an
    #: index, instead of generating a page number and object id (pdf/objects.py).
    #: Gold carries a page on 149/149 validation evidence items and an object id
    #: on every non-text_span item, so both halves of the key are graded exactly
    #: and both are transcribable from the PDF.
    use_pdf_locators: bool = True
    max_papers_to_read: int = 3
    read_confidence_floor: float = 0.35
    #: INERT at 0.0, and it should stay that way. See `collect_evidence`: an
    #: empty evidence list and a wrong one both score F1=0.0 against non-empty
    #: gold, so filtering can only ever lose points. Kept as a knob so the
    #: ablation harness can re-measure the claim rather than trust this comment.
    evidence_confidence_floor: float = 0.0

    # -- stage E
    mc_samples: int = 3
    #: Table row keys from a dedicated question-only call (see solve.py).
    extract_row_keys: bool = False


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
    #: Papers pinned by an unambiguous title-n-gram match.
    pinned: list[str] = field(default_factory=list)
    #: Non-empty when stage D or E failed but paper selection survived.
    read_error: str = ""
    answer_error: str = ""


class Pipeline:
    def __init__(
        self,
        pool: PaperPool,
        *,
        config: PipelineConfig | None = None,
        client: GeminiClient | None = None,
        fetcher: PDFFetcher | None = None,
        dense: DenseRetriever | None = None,
        reader: Any = None,
        select_client: Any = None,
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
        self.reranker = CrossEncoderReranker(
            pool, prior_weight=self.config.rerank_prior_weight
        ) if self.config.use_reranker else None
        self.selector = MentionAnchoredSelector(
            pool, self.nicknames, self.acronyms or AcronymIndex(pool), self.bm25, self.dense
        )
        # Any object with PaperReader's `read()` signature: the hosted reader,
        # or `reason.local_llm.LocalReader` running on the GPU with no quota.
        self.llm_selector = LLMPaperSelector(
            pool, select_client if select_client is not None else client, shortlist=self.config.llm_shortlist,
            samples=self.config.llm_select_samples,
            model=self.config.llm_select_model
        ) if (self.config.use_llm_selector and (select_client or client) is not None) else None
        self.visual_table = VisualTableSolver(
            client, self.fetcher
        ) if (self.config.visual_table_cells and client is not None) else None
        self.reader = reader if reader is not None else (
            PaperReader(client) if client is not None else None
        )
        # The solver still needs the hosted client for table synthesis. With a
        # local reader and no key, table questions fall back to row keys built
        # from the question and the paper titles.
        self.solver = AnswerSolver(
            client, mc_samples=self.config.mc_samples,
            extract_row_keys=self.config.extract_row_keys,
        ) if client else None

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

        if self.reranker is not None and ranked:
            ranked = [
                c.paper.paper_id
                for c in self.reranker.rerank(
                    question.question, ranked,
                    mentions=trace.mentions, mode=cfg.rerank_mode,
                )
            ]

        # A mention that matches exactly one title n-gram is the strongest signal
        # in this system, and it was being outvoted. "How many subfigures are
        # there in Figure 4 of the DynaPipe paper?" resolves to a single pool
        # entry at score 1.0 -- "DynaPipe" appears in exactly one of the 27,487
        # titles -- yet RRF fusion and the cross-encoder together pushed it out
        # of first place and the question scored paper F1 0.00. The lift applied
        # to acronym hits above happens *before* reranking, so the reranker
        # undoes it. Pin these after, where nothing can reorder them.
        if cfg.pin_exact_title_matches:
            trace.pinned = self._exact_title_matches(trace.mentions)
            for paper_id in reversed(trace.pinned):
                if paper_id in ranked:
                    ranked.remove(paper_id)
                ranked.insert(0, paper_id)

        trace.candidates = ranked

        if self.llm_selector is not None and ranked:
            selection = self.llm_selector.select(question.question, ranked)
            if selection.paper_ids:
                trace.paper_ids = selection.paper_ids[: cfg.max_set_size]
                trace.seeds = trace.paper_ids
                trace.predicted_size = len(trace.paper_ids)
                trace.size_reason = f"llm-selected (expected {selection.expected_count})"
                return trace

        if cfg.selection == "mention_anchored":
            trace.paper_ids = self.selector.select(
                question.question, trace.mentions, scope=trace.scope,
                fallback_ranked=ranked, max_papers=cfg.max_set_size,
            )
            prediction = predict_set_size(question.question)
            trace.predicted_size = len(trace.paper_ids)
            trace.size_reason = f"mention-anchored ({prediction.reason})"
            trace.seeds = trace.paper_ids
            return trace

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

    def _exact_title_matches(self, mentions: list[str]) -> list[str]:
        """Papers a mention pins unambiguously: one title n-gram hit, and only one.

        Deliberately strict. Two papers sharing the n-gram means the mention does
        not identify either of them, so nothing is pinned and the ranker decides
        as before.
        """
        pinned: list[str] = []
        for mention in mentions:
            hits = self.nicknames.lookup(mention, limit=8)
            title_hits = [p for p, score in hits if score >= NicknameIndex.TITLE_SCORE]
            if len(title_hits) == 1 and title_hits[0].paper_id not in pinned:
                pinned.append(title_hits[0].paper_id)
        return pinned

    # -- stage D: read the PDFs ------------------------------------------------

    def read_papers(self, question: Question, trace: QuestionTrace) -> list[Reading]:
        if self.reader is None:
            return []
        options = (
            question.multiple_choice_options
            if "multiple_choice" in question.answer_types
            else None
        )
        readings: list[Reading] = []
        for paper_id in trace.paper_ids[: self.config.max_papers_to_read]:
            paper: Paper = self.pool[paper_id]
            result = self.fetcher.fetch(paper)
            if not result.ok:
                trace.fetch_failures.append(paper_id)
                continue
            candidates = (
                objects_in_pdf(result.path, paper_id)
                if self.config.use_pdf_locators
                else []
            )
            readings.append(
                self.reader.read(
                    question, paper, result.path,
                    trust_pages=result.pagination_trusted,
                    options=options,
                    candidates=candidates,
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
            table = self.solver.solve_table(question, readings, titles, papers)
            if self.visual_table is not None and table.get("rows"):
                # Row keys are already decided above; the image only supplies
                # cell values. Falls back silently to the digest-built table
                # when no page can be rendered or the call fails.
                filled = self.visual_table.fill_cells(
                    question, table["rows"], readings, papers, self.pool.by_id
                )
                if filled and filled.get("rows"):
                    table = filled
            parts["table"] = table
        if "freeform" in question.answer_types:
            parts["freeform"] = self.solver.solve_freeform(question, readings, titles)
        return parts

    def collect_evidence(self, readings: list[Reading]) -> list[dict[str, Any]]:
        """Evidence from every reading, believed or not.

        The precision argument for withholding low-confidence evidence does not
        survive contact with `evaluate.prf`. Gold evidence is non-empty on all 55
        validation questions, and for non-empty gold the function returns F1=0.0
        for an empty prediction *and* F1=0.0 for a wrong one. Abstaining is
        therefore never better than guessing, and is strictly worse whenever the
        guess would have been right. The floor was costing us the 29-of-71
        questions that emitted no evidence at all in `test_v2_rerank.jsonl`.
        """
        floor = self.config.evidence_confidence_floor
        out: list[dict[str, Any]] = []
        for reading in readings:
            if reading.confidence >= floor:
                out.extend(reading.to_evidence_records())
        return out

    # -- full run --------------------------------------------------------------

    def run_question(self, question: Question) -> tuple[dict[str, Any], QuestionTrace]:
        """Answer one question, degrading stage by stage rather than all at once.

        Stages A-C are local, free and deterministic; stage D spends API quota
        and is the only part that can fail for reasons outside this process. They
        used to share one try block in the runner, so a depleted daily quota on
        question 3 discarded the paper selection for questions 3-71 as well --
        emitting empty `gold_papers` and scoring zero on the 36.4% of the total
        that retrieval alone had already earned. Whatever the reader does, the
        papers we already picked are kept.
        """
        trace = self.select_papers(question)

        readings: list[Reading] = []
        try:
            readings = self.read_papers(question, trace)
        except Exception as exc:  # noqa: BLE001 -- quota, network, SDK, anything
            trace.read_error = str(exc)
        trace.readings = readings

        try:
            answer_parts = self.build_answer(question, trace, readings)
        except Exception as exc:  # noqa: BLE001
            trace.answer_error = str(exc)
            answer_parts = {}

        record = build_record(
            question, trace.paper_ids, self.collect_evidence(readings), answer_parts
        )
        return record, trace
