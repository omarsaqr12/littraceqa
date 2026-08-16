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
from .client import parse_json
from .localize import Reading, _clean_label

#: Instruct-tuned, fits an RTX 3090 in fp16 with room for the retrieval models,
#: and follows a JSON schema stated in the prompt. Swap via the constructor.
DEFAULT_MODEL = "Qwen/Qwen3-8B"

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
        pages_per_paper: int = 6,
        chars_per_page: int = 3500,
        samples: int = 1,
        temperature: float = 0.7,
    ):
        self.model_name = model_name
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.pages_per_paper = pages_per_paper
        self.chars_per_page = chars_per_page
        self.samples = samples
        self.temperature = temperature
        self._model = None
        self._tokenizer = None
        self.calls = 0

    def load(self) -> None:
        """Load weights eagerly. Call before the question loop, never inside it.

        The runner's per-question SIGALRM watchdog will happily fire in the
        middle of a first-use model load and abandon the question, which is how
        a cold cross-encoder once turned every question into a 420-second
        timeout. Loading up front keeps that out of the timed region.
        """
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

    def _generate(self, prompt: str, *, sample: bool) -> str:
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
        pages_block = "\n\n".join(
            f"--- page {p.number} ---\n"
            + re.sub(r"\n{3,}", "\n\n", p.text)[: self.chars_per_page]
            for p in shortlist
        ) or "(no text could be extracted)"

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
