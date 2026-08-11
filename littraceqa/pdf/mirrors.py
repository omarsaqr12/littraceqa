"""Title-indexed mirrors for the venues OpenReview will not serve us.

`pdf_url` points at openreview.net for all 12,035 ICLR/ICML/NeurIPS papers, and
openreview.net answers automated requests with

    403 {"name": "ChallengeRequiredError", "message": "Challenge verification required"}

`arxiv_id` and `doi` are null for every row in the pool, so there is no metadata
fallback. Two of the three venues publish the same camera-ready PDFs elsewhere:

    ICML 2025    -> proceedings.mlr.press/v267/
    NeurIPS 2025 -> papers.nips.cc/paper_files/paper/2025

Both are indexed by title only, so we scrape each index once, key it by
`squash(title)`, and cache it to disk. ICLR has no such mirror -- it needs either
an authenticated OpenReview session or the arXiv fallback (see `fetch.py`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from ..textnorm import squash

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / "mirrors"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

PMLR_ICML_2025 = "https://proceedings.mlr.press/v267/"
NEURIPS_2025 = "https://papers.nips.cc/paper_files/paper/2025"


def _get(url: str, timeout: int = 90) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
    response.raise_for_status()
    return response.text


def _load_cached(name: str) -> dict[str, str] | None:
    path = CACHE_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_cached(name: str, mapping: dict[str, str]) -> dict[str, str]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{name}.json").write_text(
        json.dumps(mapping, ensure_ascii=False), encoding="utf-8"
    )
    return mapping


# Each paper is a <div class="paper"> block holding <p class="title">Title</p>
# and a links paragraph. Note the PDF is served from raw.githubusercontent.com
# (mlresearch/<volume>), not from proceedings.mlr.press itself.
_PMLR_TITLE = re.compile(r'<p class="title">(.*?)</p>', re.S)
_PMLR_PDF = re.compile(r'href="(https?://[^"]+\.pdf)"')
_TAGS = re.compile(r"<[^>]+>")


def build_pmlr_index(url: str = PMLR_ICML_2025, refresh: bool = False) -> dict[str, str]:
    """`squash(title) -> pdf url` for a PMLR volume (ICML 2025 = v267)."""
    name = f"pmlr_{url.rstrip('/').rsplit('/', 1)[-1]}"
    if not refresh and (cached := _load_cached(name)) is not None:
        return cached
    html = _get(url)
    mapping: dict[str, str] = {}
    for block in html.split('<div class="paper">')[1:]:
        title_match = _PMLR_TITLE.search(block)
        pdf_match = _PMLR_PDF.search(block)
        if title_match and pdf_match:
            key = squash(_TAGS.sub("", title_match.group(1)))
            if key:
                mapping.setdefault(key, pdf_match.group(1))
    return _save_cached(name, mapping)


# papers.nips.cc links each paper as
#   <a title="..." href="/paper_files/paper/2025/hash/<h>-Abstract-Conference.html">Title</a>
# and the PDF lives at .../paper/2025/file/<h>-Paper-Conference.pdf
_NIPS_LINK = re.compile(
    r'href="(/paper_files/paper/(\d{4})/hash/([0-9a-f]+)-Abstract-([A-Za-z_]+)\.html)"[^>]*>(.*?)</a>',
    re.S,
)


def build_neurips_index(url: str = NEURIPS_2025, refresh: bool = False) -> dict[str, str]:
    """`squash(title) -> pdf url` for a papers.nips.cc year index."""
    name = f"neurips_{url.rstrip('/').rsplit('/', 1)[-1]}"
    if not refresh and (cached := _load_cached(name)) is not None:
        return cached
    html = _get(url)
    mapping: dict[str, str] = {}
    for _, year, digest, track, title_html in _NIPS_LINK.findall(html):
        title = _TAGS.sub("", title_html)
        key = squash(title)
        if not key:
            continue
        mapping.setdefault(
            key,
            f"https://papers.nips.cc/paper_files/paper/{year}/file/{digest}-Paper-{track}.pdf",
        )
    return _save_cached(name, mapping)


class MirrorResolver:
    """Lazily-built, disk-cached title -> PDF-url maps for OpenReview venues."""

    def __init__(self) -> None:
        self._indices: dict[str, dict[str, str]] = {}

    def _index_for(self, venue: str, year: int) -> dict[str, str] | None:
        key = f"{venue.lower()}{year}"
        if key not in self._indices:
            try:
                if venue.lower() == "icml" and year == 2025:
                    self._indices[key] = build_pmlr_index()
                elif venue.lower() == "neurips":
                    self._indices[key] = build_neurips_index(
                        f"https://papers.nips.cc/paper_files/paper/{year}"
                    )
                else:
                    self._indices[key] = {}
            except Exception:
                self._indices[key] = {}
        return self._indices[key] or None

    def resolve(self, title: str, venue: str, year: int) -> str | None:
        index = self._index_for(venue, year)
        if not index:
            return None
        key = squash(title)
        if key in index:
            return index[key]
        # Titles differ in trailing punctuation or a dropped subtitle often enough
        # to be worth one prefix pass.
        for candidate_key, url in index.items():
            if candidate_key.startswith(key[:60]) or key.startswith(candidate_key[:60]):
                return url
        return None
