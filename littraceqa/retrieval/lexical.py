"""Lexical retrieval over the paper pool: BM25 plus squashed-nickname lookup.

Two complementary signals:

* `BM25Index` -- classic bag-of-words scoring over title+abstract. Good when the
  question paraphrases a paper's topic ("topology-aware node description synthesis").
* `NicknameIndex` -- artefact-name lookup that is blind to spacing and punctuation.
  Good when the question names something ("AceMath", "EVEv2.0", "sCM", "IMM").
  This is the highest-precision signal available and it costs nothing.

The nickname index is built over *concatenations of adjacent title tokens* rather
than raw substrings. The pool's titles carry a spacing artefact -- "AceMath" is
stored as "A ce M ath" -- so token-boundary matching alone fails, while raw
substring matching makes short acronyms ("ECM", "IMM") match everything. Joining
1-4 adjacent tokens and squashing the result gets both: "ace"+"math" -> "acemath"
matches the nickname exactly, and "ecm" only matches a real token.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from ..corpus import Paper, PaperPool
from ..textnorm import acronym_variants, clean, squash, tokens

#: Terms that look like artefact names but are ubiquitous in ML papers. Matching
#: on these floods the candidate list with thousands of irrelevant papers.
_NICKNAME_STOPLIST = {
    squash(w) for w in (
        "the", "and", "for", "with", "llm", "llms", "vlm", "vlms", "mllm", "mllms",
        "ai", "ml", "nlp", "cv", "gpu", "cpu", "api", "sota", "gpt", "bert", "clip",
        "rag", "lora", "mlp", "cnn", "rnn", "vit", "nerf", "sft", "rl", "rlhf",
        "model", "models", "method", "methods", "paper", "papers", "dataset",
        "datasets", "benchmark", "benchmarks", "figure", "table", "equation",
        "imagenet", "coco", "cifar", "mmlu", "gsm8k", "squad", "glue", "wmt",
        "transformer", "transformers", "attention", "diffusion", "baseline",
    )
}

#: Nouns that follow an artefact name and mark it as one: "the ECM paper".
_ARTEFACT_HEADS = (
    "paper", "papers", "method", "methods", "model", "models", "framework",
    "frameworks", "approach", "approaches", "dataset", "datasets", "benchmark",
    "benchmarks", "work", "works", "system", "systems", "algorithm", "architecture",
)


class BM25Index:
    """Okapi BM25 with an inverted index. ~27K docs, so pure Python is fine."""

    def __init__(self, pool: PaperPool, k1: float = 1.2, b: float = 0.75):
        self.pool = pool
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.doc_len: list[int] = []
        for index, paper in enumerate(pool.papers):
            counts = Counter(paper.doc_tokens)
            self.doc_len.append(sum(counts.values()) or 1)
            for term, freq in counts.items():
                self.postings[term].append((index, freq))
        self.n_docs = len(pool.papers)
        self.avg_len = sum(self.doc_len) / max(self.n_docs, 1)
        self.idf = {
            term: math.log(1 + (self.n_docs - len(plist) + 0.5) / (len(plist) + 0.5))
            for term, plist in self.postings.items()
        }

    def score(self, query: str, candidates: set[int] | None = None) -> dict[int, float]:
        scores: dict[int, float] = defaultdict(float)
        for term in tokens(query):
            plist = self.postings.get(term)
            if plist is None:
                continue
            idf = self.idf[term]
            for index, freq in plist:
                if candidates is not None and index not in candidates:
                    continue
                norm = 1 - self.b + self.b * self.doc_len[index] / self.avg_len
                scores[index] += idf * freq * (self.k1 + 1) / (freq + self.k1 * norm)
        return scores

    def search(
        self, query: str, top_k: int = 50, candidates: set[int] | None = None
    ) -> list[tuple[Paper, float]]:
        scores = self.score(query, candidates)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
        return [(self.pool.papers[i], s) for i, s in ranked]


class NicknameIndex:
    """Spacing-blind, boundary-respecting lookup of artefact names."""

    #: Longest run of adjacent title tokens joined into one lookup key.
    MAX_GRAM = 4
    #: Below this squashed length a nickname is too ambiguous to trust at all.
    MIN_LEN = 3
    #: Below this length we only accept title matches, never abstract matches.
    MIN_LEN_ABSTRACT = 5

    TITLE_SCORE = 1.0
    ABSTRACT_SCORE = 0.55

    def __init__(self, pool: PaperPool):
        self.pool = pool
        self.title_grams: dict[str, list[int]] = defaultdict(list)
        for index, paper in enumerate(pool.papers):
            title_tokens = tokens(paper.title)
            for start in range(len(title_tokens)):
                for size in range(1, self.MAX_GRAM + 1):
                    if start + size > len(title_tokens):
                        break
                    key = squash("".join(title_tokens[start:start + size]))
                    if len(key) >= self.MIN_LEN:
                        self.title_grams[key].append(index)
        for key, indices in self.title_grams.items():
            self.title_grams[key] = sorted(set(indices))

    def lookup(
        self,
        nickname: str,
        search_abstract: bool = True,
        restrict: set[int] | None = None,
        limit: int = 40,
    ) -> list[tuple[Paper, float]]:
        """Papers whose title (1.0) or abstract (0.55) contains `nickname`."""
        hits: dict[int, float] = {}
        variants = {v for v in acronym_variants(nickname) if len(v) >= self.MIN_LEN}
        variants -= _NICKNAME_STOPLIST
        if not variants:
            return []

        for variant in variants:
            for index in self.title_grams.get(variant, ()):
                if restrict is None or index in restrict:
                    hits[index] = max(hits.get(index, 0.0), self.TITLE_SCORE)

        # Abstract fallback: only for names long enough that a substring hit means
        # something, and only when the title index came up short.
        if search_abstract and len(hits) < limit:
            long_variants = {v for v in variants if len(v) >= self.MIN_LEN_ABSTRACT}
            if long_variants:
                for index, paper in enumerate(self.pool.papers):
                    if index in hits or (restrict is not None and index not in restrict):
                        continue
                    if any(v in paper.text_squashed for v in long_variants):
                        hits[index] = self.ABSTRACT_SCORE
                        if len(hits) >= limit * 3:
                            break

        ranked = sorted(
            ((self.pool.papers[i], s) for i, s in hits.items()),
            key=lambda ps: (-ps[1], len(ps[0].title_squashed)),
        )
        return ranked[:limit]


# --- nickname extraction from question text (no LLM needed) -------------------

# Two capitalised chunks glued together: "AceMath", "DiTFastAttnV2", "EVEv2.0".
_CAMEL = re.compile(r"\b[A-Za-z][a-z0-9]*(?:[A-Z][A-Za-z0-9]*)+(?:[.\-][A-Za-z0-9]+)*\b")
# Acronyms, incl. 2-char ones: "IMM", "VTI", "ECM", "S-RAG", "X2I".
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,}(?:[-‑][A-Za-z0-9]+)*\b")
# "Stable-Score-Distillation", "Llama-3.1-8B".
_HYPHEN_CAP = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")
_QUOTED = re.compile(r"['\"“”‘’]([^'\"“”‘’]{3,60})['\"“”‘’]")
# "the ECM paper", "the IMM method", "AccidentalGS evaluation".
_ARTEFACT_HEAD = re.compile(
    r"\b([A-Za-z][A-Za-z0-9.\-]{1,30})\s+(?:" + "|".join(_ARTEFACT_HEADS) + r")\b"
)
# "in X, ..." / "introduces X" / "proposes X".
_INTRODUCES = re.compile(
    r"\b(?:introduces?|proposes?|presents?|called|named|dubbed)\s+([A-Za-z][A-Za-z0-9.\-]{2,30})\b"
)

_SENTENCE_START_STOP = {
    "the", "this", "these", "those", "in", "for", "what", "which", "how", "among",
    "across", "compare", "comparing", "considering", "consider", "report", "give",
    "list", "and", "but", "both", "when", "where", "does", "do", "is", "are", "two",
    "iclr", "icml", "cvpr", "iccv", "eccv", "acl", "naacl", "emnlp", "neurips",
}


def extract_nicknames(question: str, max_names: int = 12) -> list[str]:
    """Heuristic artefact-name candidates from a question.

    LitTraceQA questions nearly always name the method, dataset, or model in
    question, so this cheap pass carries most of the retrieval signal. It is
    deliberately high-recall: `NicknameIndex` and RRF handle the false positives.
    Ordering matters -- earlier patterns are more reliable, and callers truncate.
    """
    text = clean(question)
    found: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = name.strip(".,;:()[]'\"")
        key = squash(name)
        if (
            not key
            or key in seen
            or key in _NICKNAME_STOPLIST
            or key in _SENTENCE_START_STOP
            or len(key) < NicknameIndex.MIN_LEN
        ):
            return
        seen.add(key)
        found.append(name)

    # Highest precision first: explicitly flagged as an artefact.
    for match in _ARTEFACT_HEAD.finditer(text):
        add(match.group(1))
    for match in _INTRODUCES.finditer(text):
        add(match.group(1))
    for pattern in (_CAMEL, _HYPHEN_CAP, _ACRONYM):
        for match in pattern.finditer(text):
            add(match.group(0))
    for match in _QUOTED.finditer(text):
        add(match.group(1))

    return found[:max_names]
