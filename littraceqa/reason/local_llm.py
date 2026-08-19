"""A reader that runs on the local GPU instead of spending API quota.

Why this exists
---------------
The hosted path is quota-bound, not capability-bound. On the current key
`gemini-3.5-flash` and `gemini-3.7-flash` return per-day 429s after roughly two
requests, so every run is carried by `gemini-flash-lite-latest` -- the weakest
model in the chain -- and a full 71-question test run costs ~120 of its calls.
That budget rules out the things that actually buy accuracy: reading all three
candidate papers, and real self-consistency over several samples.

A local model has no such ceiling. It is slower per call and smaller, but calls
are free, so it can be spent freely where the hosted path could not.

What it does *not* need to be good at
-------------------------------------
This reader is not asked to find a page number. `littraceqa/pdf/objects.py`
already enumerates every locator the PDF supports, with pages taken from the
PyMuPDF page index, and the model's whole locator job is to pick an index out of
that list. Since 70.1% of the score is paper F1 plus evidence F1, and evidence
keys are (page, object_id) pairs that are *printed in the paper*, a text-only
model with the caption list in front of it is not obviously worse here than a
vision model guessing page numbers.

The cost is figure questions, where the value is in the image and PyMuPDF
returns nothing. Those are 18 of 149 gold evidence items; the locator is still
recoverable from the caption even when the value is not.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from math import log
from pathlib import Path
from typing import Any

from ..corpus import Paper, Question
from ..pdf.objects import EvidenceCandidate, format_candidates
from ..pdf.read import PaperText, load_text
from ..textnorm import clean, tokens
from .client import RateLimiter, parse_json
from .localize import Reading, _clean_label

#: Instruct-tuned, fits an RTX 3090 in fp16 with room for the retrieval models,
#: and follows a JSON schema stated in the prompt. Swap via the constructor.
DEFAULT_MODEL = "Qwen/Qwen3-8B"

#: Smoke-tested end to end on q_001 with HuggingFaceTB/SmolLM2-1.7B-Instruct,
#: which was already in the local HF cache. A 1.7B model returned the correct
#: freeform answer ("14.70") *and* the correct multiple-choice label ("C"); only
#: the locator was wrong, picking "Figure 2 page 2" where gold is "Table 4 page
#: 6". So the plumbing works and the answer side is not the hard part -- picking
#: the right index out of the candidate list is. Expect a competent 8B to do
#: materially better on that, and check it before trusting the numbers.
#:
#: MIND THE CONTEXT WINDOW. Six pages at 3500 chars plus the candidate list ran
#: to ~8950 tokens on that test, which overflowed SmolLM2's 8192 and produced a
#: transformers warning. Qwen3-8B has 32k so the defaults are safe there; drop
#: `pages_per_paper` or `chars_per_page` for any model with a smaller window.

PROMPT = """You are reading one paper from a scientific-literature QA benchmark.

PAPER
  title: {title}
  venue: {venue} {year}

QUESTION
{question}

RELEVANT PAGES OF THE PAPER (text extracted from the PDF)
{pages}

CANDIDATE LOCATIONS IN THIS PDF
These were extracted mechanically from the PDF. The page numbers are exact and
the object labels are the ones actually printed in it.

{candidates}
{options_block}
Answer the question from the pages above, then say where the answer came from.

Rules:
- `evidence_index` is a list of indices into the candidate list, usually exactly
  one. Choose the most specific entry that fits: prefer the table, figure or
  equation the value is printed in over that page's prose entry.
- Running prose is the RAREST source in this benchmark, not the safest. Gold
  evidence is a table 31% of the time, a figure 27%, prose only 16%, a reference
  13%, an equation 13%. A reported number almost always belongs to the table or
  figure it is printed in, even when nearby prose repeats it.
- Never return an empty `evidence_index`. An empty answer and a wrong answer
  score exactly the same zero, so always commit to your best guess and put your
  uncertainty in `confidence` instead.
- `answer` is the value alone, no explanation: "14.70", "Freda Shi", "8".

Reply with ONLY a JSON object, no other text:
{{"found": true, "answer": "...", "quote": "...", "confidence": 0.0,{label_field}
 "evidence_index": [0]}}"""

OPTIONS_BLOCK = """
MULTIPLE-CHOICE OPTIONS
{options}

Also set `label` to the letter best supported by the pages above. Judge the
options against what the paper says, not your own recollection. Commit to a
letter even if the match is imperfect; there is no credit for abstaining.
"""


#: Grammar for the served backend. `evidence_index` is deliberately an array of
#: integers with no maximum: constraining it to one entry would forbid the
#: multi-location answers that some questions genuinely need.
READ_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "quote": {"type": "string"},
        "confidence": {"type": "number"},
        "label": {"type": "string"},
        "evidence_index": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["found", "answer", "confidence", "evidence_index"],
}


@dataclass(slots=True)
class _Page:
    number: int
    text: str
    score: float = 0.0


def shortlist_pages(question: str, text: PaperText, k: int = 6) -> list[_Page]:
    """The `k` pages most likely to hold the answer, by idf-weighted overlap.

    A whole paper is 10-20k tokens, which fits the context window but degrades
    an 8B model's attention to the one table that matters. Scoring is local and
    costs nothing, so it is worth doing even though it can drop the right page:
    the candidate locator list still carries every page's captions, so a wrong
    shortlist loses the *value* but not necessarily the locator.
    """
    pages = [_Page(i, t) for i, t in enumerate(text.pages, start=1) if t.strip()]
    if not pages:
        return []

    query = set(tokens(question))
    if not query:
        return pages[:k]

    # Document frequency over pages, so boilerplate in every header counts for
    # little and a dataset name appearing on two pages counts for a lot.
    document_frequency: Counter[str] = Counter()
    page_tokens: list[set[str]] = []
    for page in pages:
        seen = set(tokens(page.text))
        page_tokens.append(seen)
        document_frequency.update(seen & query)

    n = len(pages)
    for page, seen in zip(pages, page_tokens):
        page.score = sum(
            log(1 + n / (1 + document_frequency[term]))
            for term in query & seen
        )

    ranked = sorted(pages, key=lambda p: (-p.score, p.number))[:k]
    return sorted(ranked, key=lambda p: p.number)


class LocalReader:
    """Same `read()` contract as `localize.PaperReader`, no API quota."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        device: str = "cuda",
        max_new_tokens: int = 512,
        # gpt-oss-120b spends reasoning_tokens before the JSON body; 512 truncated
        # the answer on q_001 and produced 'no parseable JSON'.
        hosted_max_new_tokens: int = 2048,
        pages_per_paper: int = 6,
        chars_per_page: int = 3500,
        samples: int = 1,
        temperature: float = 0.7,
        base_url: str | None = None,
        api_key: str | None = None,
        context_tokens: int | None = None,
        timeout: float = 300.0,
        rpm: int = 0,
    ):
        self.model_name = model_name
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.hosted_max_new_tokens = hosted_max_new_tokens
        self.pages_per_paper = pages_per_paper
        self.chars_per_page = chars_per_page
        self.samples = samples
        self.temperature = temperature
        #: OpenAI-compatible endpoint (llama-server, vLLM, ...). When set, the
        #: model is reached over HTTP and transformers is never imported.
        #: This is how the 27B GGUF is usable at all: the only HF-format models
        #: on this box are a 0.5B instruct, a 3B *base* (no chat tuning) and a
        #: 2B VL, none of which can be trusted to emit schema-shaped JSON.
        self.base_url = base_url.rstrip("/") if base_url else None
        #: Bearer token for hosted OpenAI-compatible providers (Cerebras, Groq).
        self.api_key = api_key
        #: Prompt budget. llama-server here runs --ctx-size 4096, and the
        #: defaults above build a ~9k-token prompt, so it must be trimmed or the
        #: server silently truncates the front -- taking the pages with it.
        self.context_tokens = context_tokens
        self.timeout = timeout
        #: Hosted providers cap requests per minute even on paid tiers -- Cerebras
        #: returns 429 request_quota_exceeded. Unlimited firing produced 51 errors
        #: in 10 questions.
        self.limiter = RateLimiter(rpm)
        self._model = None
        self._tokenizer = None
        self._session = None
        self.calls = 0
        self.truncated = 0

    def load(self) -> None:
        """Load weights eagerly. Call before the question loop, never inside it.

        The runner's per-question SIGALRM watchdog will happily fire in the
        middle of a first-use model load and abandon the question, which is how
        a cold cross-encoder once turned every question into a 420-second
        timeout. Loading up front keeps that out of the timed region.
        """
        if self.base_url is not None:
            # Served model: nothing to load locally, but fail loudly here rather
            # than 71 questions deep if the server is not actually up.
            import requests

            self._session = requests.Session()
            if self.api_key:
                self._session.headers["Authorization"] = f"Bearer {self.api_key}"
            response = self._session.get(f"{self.base_url}/v1/models", timeout=15)
            response.raise_for_status()
            return
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            dtype=torch.float16,
            device_map={"": self.device},
        )
        self._model.eval()

    @property
    def model(self):
        self.load()
        return self._model

    def _generate_served(self, prompt: str, *, sample: bool) -> str:
        """One chat completion against an OpenAI-compatible server.

        Output is grammar-constrained to `READ_SCHEMA`. Unconstrained, Qwen3.6
        narrates its reasoning first ("To determine the number of subfigures, we
        examine...") and runs out of tokens before emitting any JSON: 2 of the
        first 3 smoke-test questions returned nothing parseable. Constraining the
        response makes that failure mode structurally impossible, which matters
        more here than letting the model think out loud, since the prompt already
        does the hard part by handing it an enumerated candidate list.
        """
        if self._session is None:
            self.load()
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": (self.hosted_max_new_tokens if self.api_key
                           else self.max_new_tokens),
            "temperature": self.temperature if sample else 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "reading", "schema": READ_SCHEMA},
            },
        }
        if self.api_key is None:
            # llama.cpp extension: Qwen3 thinks by default under --jinja and the
            # reasoning block would consume max_tokens before any JSON appears.
            # Hosted providers reject unknown fields -- Cerebras returns
            # 400 "property 'chat_template_kwargs' is unsupported" -- and that
            # 400 silently emptied every reading in a whole validation run.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if sample:
            payload["top_p"] = 0.9
        self.limiter.acquire()
        response = self._session.post(
            f"{self.base_url}/v1/chat/completions", json=payload, timeout=self.timeout
        )
        response.raise_for_status()
        self.calls += 1
        body = response.json()
        return (body.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""

    def _generate(self, prompt: str, *, sample: bool) -> str:
        if self.base_url is not None:
            return self._generate_served(prompt, sample=sample)
        import torch

        tokenizer = self._tokenizer
        messages = [{"role": "user", "content": prompt}]
        try:
            # Qwen3 emits a <think> block unless this is switched off, which
            # would eat the whole token budget before any JSON appeared.
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:  # template without the Qwen3 thinking switch
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

        inputs = tokenizer([text], return_tensors="pt").to(self.model.device)
        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=sample,
                temperature=self.temperature if sample else None,
                top_p=0.9 if sample else None,
                pad_token_id=tokenizer.eos_token_id,
            )
        self.calls += 1
        generated = output[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(generated, skip_special_tokens=True)

    #: Rough chars-per-token for English prose plus LaTeX-ish noise. Only used to
    #: size the prompt, so an approximation that errs small is fine.
    CHARS_PER_TOKEN = 3.6

    def _fit_pages(
        self,
        shortlist: list[_Page],
        candidates: list[EvidenceCandidate],
        question: Question,
    ) -> str:
        """Render page text within the model's context budget.

        Without this the server truncates from the *front*, which silently drops
        the page text and leaves the model answering from the candidate list
        alone. Pages are trimmed evenly and the highest-scoring ones kept, since
        `shortlist_pages` already ordered them by relevance before restoring
        reading order.
        """
        if not shortlist:
            return "(no text could be extracted)"

        chars_per_page = self.chars_per_page
        pages = shortlist
        if self.context_tokens:
            # Everything that is not page text: prompt scaffolding, the question,
            # the candidate list, the options block, plus room to generate.
            overhead = (
                len(PROMPT) + len(question.question)
                + sum(len(c.describe()) + 6 for c in candidates)
                + 600
            )
            budget = int(
                (self.context_tokens - self.max_new_tokens) * self.CHARS_PER_TOKEN
            ) - overhead
            if budget < 800:  # pathological; keep one small page rather than none
                pages, chars_per_page = shortlist[:1], 800
            else:
                while len(pages) > 1 and budget // len(pages) < 900:
                    pages = pages[:-1]
                chars_per_page = min(self.chars_per_page, max(800, budget // len(pages)))
                if len(pages) < len(shortlist):
                    self.truncated += 1

        return "\n\n".join(
            f"--- page {p.number} ---\n"
            + re.sub(r"\n{3,}", "\n\n", p.text)[:chars_per_page]
            for p in pages
        ) or "(no text could be extracted)"

    def read(
        self,
        question: Question,
        paper: Paper,
        pdf_path: Path,
        *,
        trust_pages: bool = True,
        options: dict[str, str] | None = None,
        candidates: list[EvidenceCandidate] | None = None,
    ) -> Reading:
        text = load_text(paper.paper_id, Path(pdf_path))
        if text is None or not text.pages:
            return Reading(paper.paper_id, False, "", "", 0.0,
                           error="pymupdf could not read the pdf")

        candidates = list(candidates or [])
        shortlist = shortlist_pages(question.question, text, k=self.pages_per_paper)
        pages_block = self._fit_pages(shortlist, candidates, question)

        options_block = ""
        if options:
            options_block = OPTIONS_BLOCK.format(
                options="\n".join(f"  {k}. {options[k]}" for k in sorted(options))
            )
        prompt = PROMPT.format(
            title=clean(paper.title), venue=paper.venue, year=paper.year,
            question=question.question,
            pages=pages_block,
            candidates=format_candidates(candidates),
            options_block=options_block,
            label_field=' "label": "A",' if options else "",
        )

        payloads = []
        for index in range(max(1, self.samples)):
            raw = self._generate(prompt, sample=index > 0)
            parsed = parse_json(raw, None)
            if isinstance(parsed, dict):
                payloads.append(parsed)
        if not payloads:
            return Reading(paper.paper_id, False, "", "", 0.0,
                           error="no parseable JSON from local model",
                           candidates=candidates)

        # Self-consistency, which the hosted path could never afford: majority
        # vote the label and the locator, keep the answer that agrees with them.
        head = payloads[0]
        label = ""
        if options:
            votes = Counter(
                l for l in (_clean_label(p.get("label")) for p in payloads) if l in options
            )
            label = votes.most_common(1)[0][0] if votes else ""

        index_votes: Counter[int] = Counter()
        for payload in payloads:
            for i in payload.get("evidence_index") or []:
                if isinstance(i, int):
                    index_votes[i] += 1
        best_indices = [i for i, _ in index_votes.most_common(2)] if index_votes else []
        # Keep only indices at least as popular as the top one, so a single
        # sample's stray pick does not dilute precision.
        if index_votes:
            top = index_votes.most_common(1)[0][1]
            best_indices = [i for i, c in index_votes.items() if c == top][:2]

        return Reading(
            paper_id=paper.paper_id,
            found=bool(head.get("found", True)),
            answer=str(head.get("answer") or "").strip(),
            quote=str(head.get("quote") or "").strip(),
            confidence=float(head.get("confidence") or 0.5),
            evidence=[],
            label=label,
            candidates=candidates,
            evidence_index=best_indices,
        )
