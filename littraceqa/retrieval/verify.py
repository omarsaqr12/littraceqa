"""LLM selection of the final paper set from retrieved candidates.

The leaderboard makes this stage non-optional: five teams sit at paper F1 ~0.985
with MC exactly 1.000, and they are separated only by table F1. Paper retrieval
is an entry ticket, not an advantage, and purely local ranking does not reach it
-- the cross-encoder tops out at 0.490 on validation.

Why an LLM closes the gap where a reranker cannot: the questions *describe* their
papers ("the encoder-free VLM paper that introduces EVEv2.0", "the two ICCV 2025
papers, one on person re-id and one on robustifying zero-shot VLMs"). Deciding
which candidates satisfy a compound, multi-clause description is reading
comprehension, not similarity scoring. A cross-encoder gives one relevance number
per candidate independently; it cannot reason about *which two* of forty jointly
satisfy the question, nor decide how many to return.

Costs one call per question against a shortlist of titles and abstracts -- no
PDFs -- so it is cheap relative to the reading stage.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..corpus import Paper, PaperPool
from ..textnorm import clean
from ..reason.client import GeminiClient

SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "why": {"type": "string"},
                },
                "required": ["index"],
            },
        },
        "expected_count": {"type": "integer"},
    },
    "required": ["selected"],
}

PROMPT = """Identify which candidate papers a research question is about.

QUESTION
{question}

CANDIDATE PAPERS
{candidates}

The question was written against a specific set of papers. Return the index of
every paper it asks about -- no more, no fewer. Precision and recall are both
graded, so a padded list is as costly as a short one.

How to decide:
- The question usually names the artefact (a method, dataset, model, or
  benchmark). Match that name against the title and abstract. The pool's titles
  have spacing damage, so "AceMath" may appear as "A ce M ath" -- read through it.
- A question may describe a paper without naming it ("the encoder-free VLM
  paper"); match on the description instead.
- If it states a count ("the two ICCV 2025 papers"), return exactly that many.
- If it names several artefacts, each one is usually a separate paper.
- A venue or year in the question ("ICCV 2025") is a hard constraint.
- Values quoted in the question (numbers, baselines, benchmark names) are often
  *inside* the paper rather than in its abstract. Do not reject a candidate just
  because the abstract omits them.

`expected_count` is how many papers you believe the question covers, which may
differ from how many candidates deserve selecting.
"""


@dataclass(slots=True)
class Selection:
    paper_ids: list[str]
    expected_count: int
    ok: bool = True


class LLMPaperSelector:
    def __init__(
        self,
        pool: PaperPool,
        client: GeminiClient,
        *,
        shortlist: int = 20,
        abstract_chars: int = 420,
        max_selected: int = 8,
        samples: int = 1,
        model: str | None = None,
        thinking_budget: int | None = -1,
    ):
        self.pool = pool
        self.client = client
        self.shortlist = shortlist
        self.abstract_chars = abstract_chars
        self.max_selected = max_selected
        self.samples = samples
        #: Selection is ~71 calls for a whole test run, so it can afford the best
        #: model available while the reader (3x that) stays on flash-lite. The
        #: four teams at paper precision exactly 1.0000 are not doing anything
        #: cheap here.
        self.model = model
        #: -1 leaves the model's own default alone. The client disables thinking
        #: globally, which is right for the reader (small schema-bound answers)
        #: and wrong here: gemini-3.7-flash with thinking off returned exactly
        #: one paper on all 55 validation questions, against 1.31 for flash-lite
        #: and 2.65 in gold. Selection is a reasoning task over 30 candidates.
        self.thinking_budget = thinking_budget

    def _render(self, papers: list[Paper]) -> str:
        lines = []
        for index, paper in enumerate(papers):
            abstract = clean(paper.abstract)[: self.abstract_chars]
            lines.append(
                f"[{index}] {clean(paper.title)}\n"
                f"     {paper.venue} {paper.year}\n"
                f"     {abstract}"
            )
        return "\n\n".join(lines)

    def select(self, question: str, candidate_ids: list[str]) -> Selection:
        """Pick the papers, optionally voting over several independent attempts.

        Selection is now the binding constraint on paper F1, not retrieval:
        recognition accuracy is 86% of what the shortlist permits, and coverage
        saturates by top-30. On the test-like family only 1 of 62 candidate
        misses is a coverage failure — everything else is the cluster regime,
        where 77% of gold papers are never named in their own question and no
        retriever can reach them.

        Voting targets exactly that 14%: a paper chosen by a majority of
        independent passes is more likely right than one chosen once, and this
        is the cheapest accuracy available on a stage that costs one call.
        """
        candidates = [self.pool[p] for p in candidate_ids[: self.shortlist] if p in self.pool.by_id]
        if not candidates:
            return Selection([], 0, ok=False)

        prompt = PROMPT.format(question=question, candidates=self._render(candidates))
        votes: Counter[str] = Counter()
        expectations: list[int] = []
        rounds = 0
        for attempt in range(max(1, self.samples)):
            # Attempt 0 is greedy and cached; later attempts vary the cache key
            # so they are genuinely separate samples rather than the same reply.
            payload = self.client.generate_json(
                prompt if attempt == 0 else f"{prompt}\n\n(independent attempt {attempt + 1})",
                schema=SELECT_SCHEMA,
                model=self.model,
                thinking_budget=self.thinking_budget,
                max_output_tokens=4096,
                default=None,
            )
            if not isinstance(payload, dict):
                continue
            rounds += 1
            seen: set[str] = set()
            for item in payload.get("selected") or []:
                if not isinstance(item, dict):
                    continue
                index = item.get("index")
                if isinstance(index, int) and 0 <= index < len(candidates):
                    paper_id = candidates[index].paper_id
                    if paper_id not in seen:
                        seen.add(paper_id)
                        votes[paper_id] += 1
            expected = payload.get("expected_count")
            if isinstance(expected, int) and expected > 0:
                expectations.append(expected)

        if not rounds:
            return Selection([candidates[0].paper_id], 1, ok=False)

        expected = (
            sorted(expectations)[len(expectations) // 2] if expectations else len(votes)
        )
        # Keep papers a majority of attempts agreed on; if that empties the set,
        # fall back to the most-voted, since abstaining scores the same zero as
        # being wrong.
        threshold = (rounds + 1) // 2
        chosen = [p for p, n in votes.most_common() if n >= threshold]
        if not chosen:
            chosen = [p for p, _ in votes.most_common(max(1, expected))]
        if not chosen:
            return Selection([candidates[0].paper_id], expected, ok=False)
        return Selection(chosen[: self.max_selected], expected)
