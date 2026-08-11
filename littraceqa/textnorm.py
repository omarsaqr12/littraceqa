"""Text normalisation for LitTraceQA.

The paper pool's ``title`` field is machine-extracted and 7.5% of titles carry a
spacing artefact where an interior capital is split off from its word:

    "500xCompressor"  ->  "500x C ompressor"
    "100-LongBench"   ->  "100- L ong B ench"
    "AceMath"         ->  "A ce M ath"

Method nicknames in questions ("AceMath", "500xCompressor", "HateSieve") are
written the normal way, so naive token matching misses these papers entirely.
`squash` collapses a string to lowercase alphanumerics only, which makes both
spellings identical and turns nickname lookup into a substring test.
"""

from __future__ import annotations

import html
import re
import unicodedata

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# A lone capital followed by a lowercase run: the mangling signature.
_SPLIT_CAP = re.compile(r"\b([A-Z]) ([a-z])")


def unescape(text: str) -> str:
    """Metadata titles keep raw HTML entities (``Don&#x27;t Shake the Wheel``)."""
    return html.unescape(text or "")


def unicode_fold(text: str) -> str:
    """NFKC-fold and map common typographic variants to ASCII equivalents."""
    text = unicodedata.normalize("NFKC", text or "")
    for bad, good in (
        ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
        ("–", "-"), ("—", "-"), ("−", "-"), (" ", " "),
    ):
        text = text.replace(bad, good)
    return text


def demangle(text: str) -> str:
    """Undo the ``"C ompressor" -> "Compressor"`` split-capital artefact.

    Applied repeatedly because runs like ``"A ce M ath"`` need two passes.
    This restores readable titles; it does not recover lost interior spaces
    (``"L ong B ench"`` becomes ``"Long Bench"``, not ``"LongBench"``) -- use
    `squash` when you need those to compare equal.
    """
    previous = None
    while previous != text:
        previous = text
        text = _SPLIT_CAP.sub(r"\1\2", text)
    return text


def clean(text: str) -> str:
    """Human-readable normalisation: unescape, fold, demangle, collapse spaces."""
    return _WS.sub(" ", demangle(unicode_fold(unescape(text)))).strip()


def squash(text: str) -> str:
    """Lowercase alphanumerics only -- spacing and punctuation blind.

    ``squash("500x C ompressor") == squash("500xCompressor") == "500xcompressor"``
    """
    return _NON_ALNUM.sub("", unicode_fold(unescape(text)).lower())


def tokens(text: str) -> list[str]:
    """Alphanumeric tokens of a demangled string, lowercased."""
    return _NON_ALNUM.sub(" ", clean(text).lower()).split()


def acronym_variants(name: str) -> set[str]:
    """Surface forms a method nickname might take in a title.

    ``"DiTFastAttnV2"`` also appears as ``"DiT-FastAttn-V2"`` / ``"DiT FastAttn V2"``,
    so we index the squashed form plus a hyphen/space-split of camel boundaries.
    """
    name = unicode_fold(unescape(name)).strip()
    out = {squash(name)}
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    out.add(squash(split))
    out.discard("")
    return out
