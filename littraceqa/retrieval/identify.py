"""Identify the paper, then match the title into the pool.

The hypothesis, from the leaderboard rather than from theory: four teams report
paper precision **exactly 1.0000** over a 27,487-paper pool. Our own oracle --
keep exactly the gold papers already present in the top-40 candidates -- caps at
0.756 on validation. Perfect precision is not reachable by ranking title and
abstract, and it is not plausible that four independent IR pipelines converged on
identical rows.

What does explain it: a model that knows the 2025 literature is asked *which
paper this question is about*, returns a title, and the title is matched into the
pool. ``IMM -> Inductive Moment Matching`` is a fact, not a lexical overlap. Our
own runs corroborate it -- MC accuracy is 0.82 at paper F1 0.647, so the reader
is already answering correctly on questions where we handed it the wrong paper.
The knowledge is being used downstream and refused upstream.

Matching is where `textnorm.squash` earns its place: the pool stores "AceMath" as
"A ce M ath", and squashing both sides to lowercase alphanumerics makes the two
identical. That is exactly the failure a title-similarity search would hit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from ..corpus import Paper, PaperPool
from ..reason.client import GeminiClient
from .lexical import NicknameIndex
from ..textnorm import clean, squash

IDENTIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "papers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "venue": {"type": "string"},
                    "year": {"type": "integer"},
                    "confidence": {"type": "number"},
                },
                "required": ["title"],
            },
        },
        "n_expected": {"type": "integer"},
    },
    "required": ["papers"],
}

PROMPT = """Identify the specific paper or papers a benchmark question is about.

QUESTION
{question}

These are papers from ACL, NAACL, EMNLP, CVPR, ICCV, ECCV, ICLR, ICML or NeurIPS,
almost all published in 2025 (ECCV is 2024). The question usually names the
method, dataset, model or benchmark the paper introduced -- "EVEv2.0", "AceMath",
"TokenIT", "IMM" -- and that name is often an acronym or shorthand that does not
appear in the paper's title. Expand it: "IMM" in a diffusion-distillation context
is *Inductive Moment Matching*.

Return the **exact published title** of each paper the question asks about, as it
would appear in the proceedings. Do not paraphrase or shorten it, and do not
return a title you are not reasonably confident is real -- a wrong title costs as
much as no title.

`n_expected` is how many distinct papers the question covers. If it says "the two
ICCV 2025 papers", that is 2. If it names several methods, each is usually its own
paper. If it asks about one paper's internals, that is 1.

Set `confidence` per paper between 0 and 1: how sure you are that this exact
paper is the one meant.

If you genuinely cannot identify a paper, return an empty list rather than a
guessed title.
"""


@dataclass(slots=True)
class IdentifiedPaper:
    title: str
    venue: str = ""
    year: int = 0
    confidence: float = 0.0
    #: Filled by `match_to_pool`.
    paper_id: str = ""
    match_score: float = 0.0


@dataclass(slots=True)
class Identification:
    papers: list[IdentifiedPaper] = field(default_factory=list)
    n_expected: int = 0
    ok: bool = True

    @property
    def matched_ids(self) -> list[str]:
        return [p.paper_id for p in self.papers if p.paper_id]


class PaperIdentifier:
    """Ask a knowledgeable model for titles, then resolve them against the pool."""

    #: Below this squashed-title similarity a match is more likely noise than the
    #: paper. Titles are long, so a genuine match scores very high; 88 rejects
    #: near-misses without discarding minor punctuation differences.
    MIN_MATCH = 88.0

    def __init__(
        self,
        pool: PaperPool,
        client: GeminiClient,
        *,
        model: str = "gemini-flash-lite-latest",
        use_search: bool = False,
        max_papers: int = 6,
        nicknames: NicknameIndex | None = None,
    ):
        self.pool = pool
        self.nicknames = nicknames if nicknames is not None else NicknameIndex(pool)
        self.client = client
        self.model = model
        self.use_search = use_search
        self.max_papers = max_papers
        # Squashed titles are the match keys: the pool's "A ce M ath" and a
        # model's "AceMath" both squash to "acemath".
        self._keys = [p.title_squashed for p in pool.papers]

    # -- matching --------------------------------------------------------------

    def match_to_pool(
        self, title: str, venue: str = "", year: int = 0
    ) -> tuple[str, float]:
        """Best pool paper for a returned title, or ("", 0.0).

        Matching the *whole* title is too strict, because of how the model fails.
        It reliably recovers the artefact name and then invents the subtitle:
        for gold "EasySpec: Layer-Parallel Speculative Decoding..." it returned
        "EasySpec: Making Large Language Models Faster with...", which is right
        about the only part that identifies the paper and wrong about the rest.
        Full-title fuzzy scored those 65 and 73 and rejected both.

        So match the head -- the text before the first colon -- through the same
        title n-gram index the nickname retriever uses, and keep full-title
        similarity only as corroboration.
        """
        key = squash(title)
        if not key:
            return "", 0.0

        # 1. Exact squashed full title. Unambiguous when it happens.
        for index, candidate in enumerate(self._keys):
            if candidate == key:
                return self.pool.papers[index].paper_id, 100.0

        # 2. Head of the title ("EasySpec"), looked up as a title n-gram.
        head = squash(re.split(r"[:–—-]", title, maxsplit=1)[0])
        if len(head) >= 4:
            hits = self.nicknames.lookup(head, search_abstract=False, limit=8)
            exact = [
                p for p, score in hits
                if score >= 1.0 and (not venue or p.venue.lower() == venue.lower().strip())
            ]
            if len(exact) == 1:
                return exact[0].paper_id, 95.0
            if exact:
                # Several papers share the head; let the full title choose.
                best = max(exact, key=lambda p: fuzz.ratio(key, p.title_squashed))
                return best.paper_id, 90.0

        # 3. Fuzzy over full squashed titles.
        result = process.extractOne(key, self._keys, scorer=fuzz.ratio)
        if result is None:
            return "", 0.0
        _, score, index = result
        if score < self.MIN_MATCH:
            return "", float(score)

        paper = self.pool.papers[index]
        # Venue/year are a sanity check, not a filter: the model is more often
        # right about the title than about where it appeared.
        if venue and paper.venue.lower() != venue.lower().strip():
            score -= 4
        if year and paper.year != year:
            score -= 2
        return paper.paper_id, float(score)

    # -- identification --------------------------------------------------------

    def identify(self, question: str) -> Identification:
        config: dict = {}
        if self.use_search:
            # Grounding is free on 2.5-flash and lets the model look up a method
            # name it does not recall, which is the whole point of this stage.
            config["tools"] = [{"google_search": {}}]

        payload = self.client.generate_json(
            PROMPT.format(question=question),
            # Structured output and tool use are mutually exclusive on this API,
            # so with search on we ask for JSON in the prompt and parse leniently.
            schema=None if self.use_search else IDENTIFY_SCHEMA,
            model=self.model,
            max_output_tokens=1400,
            default=None,
            extra_config=config or None,
        )
        if not isinstance(payload, dict):
            return Identification(ok=False)

        papers: list[IdentifiedPaper] = []
        for item in (payload.get("papers") or [])[: self.max_papers]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            identified = IdentifiedPaper(
                title=title,
                venue=str(item.get("venue") or "").strip(),
                year=int(item.get("year") or 0) if str(item.get("year") or "").isdigit() else 0,
                confidence=float(item.get("confidence") or 0.5),
            )
            identified.paper_id, identified.match_score = self.match_to_pool(
                identified.title, identified.venue, identified.year
            )
            papers.append(identified)

        expected = payload.get("n_expected")
        expected = expected if isinstance(expected, int) and expected > 0 else len(papers)
        return Identification(papers=papers, n_expected=expected)


def json_from_grounded(text: str) -> dict | None:
    """Parse the JSON object out of a grounded reply.

    Search-grounded responses cannot use structured output, so the model wraps
    the object in prose or a fence often enough to need handling.
    """
    from ..reason.client import parse_json

    parsed = parse_json(text, None)
    if isinstance(parsed, dict):
        return parsed
    match = re.search(r"\{.*\}", text or "", re.S)
    return parse_json(match.group(0), None) if match else None
