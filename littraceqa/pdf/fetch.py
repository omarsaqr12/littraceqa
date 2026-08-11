"""PDF acquisition with per-venue routing, mirrors, and a disk cache.

Resolution order per paper:

1. ``pdf_url`` directly -- works for ACL/EMNLP/NAACL, CVPR/ICCV, ECCV (15,452 papers).
2. A title-indexed mirror -- ICML 2025 via PMLR, NeurIPS via papers.nips.cc (8,332).
3. An authenticated OpenReview session -- the only route for ICLR 2025 (3,703).
4. arXiv title match -- degraded fallback. Recovers the paper and the answer, but
   arXiv pagination differs from the camera-ready, so evidence page locators drift.
   Papers resolved this way are flagged so the caller can suppress page-level
   evidence rather than emit a locator it has reason to distrust.

Everything is cached by ``paper_id``; a paper is downloaded at most once.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

from ..corpus import Paper
from ..textnorm import clean, squash
from .mirrors import UA, MirrorResolver

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT / "pdf_cache"
STATUS_PATH = ROOT / "cache" / "fetch_status.json"

Source = Literal["direct", "mirror", "openreview", "arxiv", "cached", "failed"]


@dataclass(slots=True)
class FetchResult:
    paper_id: str
    path: Path | None
    source: Source
    #: True when pagination is not guaranteed to match the venue camera-ready.
    pagination_trusted: bool = True
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.path is not None


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


class PDFFetcher:
    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        *,
        allow_arxiv: bool = True,
        openreview_client=None,
        timeout: int = 60,
        polite_delay: float = 0.34,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.allow_arxiv = allow_arxiv
        self.timeout = timeout
        self.polite_delay = polite_delay
        self.mirrors = MirrorResolver()
        self._openreview = openreview_client
        self._openreview_tried = openreview_client is not None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/pdf,*/*"})
        self._last_request = 0.0
        self.status: dict[str, dict] = {}
        if STATUS_PATH.exists():
            self.status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))

    # -- helpers --------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.polite_delay:
            time.sleep(self.polite_delay - elapsed)
        self._last_request = time.time()

    def _download(self, url: str, dest: Path) -> bool:
        self._throttle()
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200 or not _looks_like_pdf(response.content):
                return False
            dest.write_bytes(response.content)
            return True
        except Exception:
            return False

    def _openreview_client(self):
        """Log in once, lazily. Returns None when credentials are absent."""
        if self._openreview_tried:
            return self._openreview
        self._openreview_tried = True
        username = os.environ.get("OPENREVIEW_USERNAME")
        password = os.environ.get("OPENREVIEW_PASSWORD")
        if not username or not password:
            return None
        try:
            import openreview

            self._openreview = openreview.api.OpenReviewClient(
                baseurl="https://api2.openreview.net", username=username, password=password
            )
        except Exception:
            self._openreview = None
        return self._openreview

    def _fetch_openreview(self, paper: Paper, dest: Path) -> bool:
        client = self._openreview_client()
        if client is None or not paper.openreview_id:
            return False
        try:
            data = client.get_attachment(paper.openreview_id, "pdf")
            if data and _looks_like_pdf(data):
                dest.write_bytes(data)
                return True
        except Exception:
            pass
        return False

    _ARXIV_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S)
    _ARXIV_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
    _ARXIV_ID = re.compile(r"<id>https?://arxiv\.org/abs/([^<]+)</id>")

    def _fetch_arxiv(self, paper: Paper, dest: Path) -> bool:
        """Title-match against the arXiv API, then download that PDF."""
        title = clean(paper.title).split(":")[0][:180]
        try:
            self._throttle()
            response = self.session.get(
                "https://export.arxiv.org/api/query",
                params={"search_query": f'ti:"{title}"', "max_results": 3},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            return False
        want = squash(paper.title)
        for entry in self._ARXIV_ENTRY.findall(response.text):
            title_match = self._ARXIV_TITLE.search(entry)
            id_match = self._ARXIV_ID.search(entry)
            if not title_match or not id_match:
                continue
            got = squash(title_match.group(1))
            if not (got.startswith(want[:50]) or want.startswith(got[:50])):
                continue
            return self._download(f"https://arxiv.org/pdf/{id_match.group(1)}", dest)
        return False

    # -- public API -----------------------------------------------------------

    def fetch(self, paper: Paper, force: bool = False) -> FetchResult:
        dest = self.cache_dir / f"{paper.paper_id}.pdf"
        if dest.exists() and dest.stat().st_size > 1024 and not force:
            prior = self.status.get(paper.paper_id, {})
            return FetchResult(
                paper.paper_id, dest, "cached",
                pagination_trusted=prior.get("pagination_trusted", True),
            )

        host = paper.pdf_url.lower()
        is_openreview = "openreview.net" in host

        if not is_openreview and paper.pdf_url and self._download(paper.pdf_url, dest):
            return self._record(paper, dest, "direct", True)

        mirror_url = self.mirrors.resolve(paper.title, paper.venue, paper.year)
        if mirror_url and self._download(mirror_url, dest):
            return self._record(paper, dest, "mirror", True)

        if is_openreview and self._fetch_openreview(paper, dest):
            return self._record(paper, dest, "openreview", True)

        # Direct openreview.net is tried last: it 403s without a session, but a
        # session may exist for some callers and it costs one request to find out.
        if is_openreview and paper.pdf_url and self._download(paper.pdf_url, dest):
            return self._record(paper, dest, "direct", True)

        if self.allow_arxiv and self._fetch_arxiv(paper, dest):
            return self._record(paper, dest, "arxiv", False)

        return self._record(paper, None, "failed", True, "no source resolved")

    def _record(
        self, paper: Paper, path: Path | None, source: Source,
        pagination_trusted: bool, error: str = "",
    ) -> FetchResult:
        self.status[paper.paper_id] = {
            "source": source,
            "pagination_trusted": pagination_trusted,
            "venue": paper.venue,
            "year": paper.year,
            "error": error,
        }
        return FetchResult(paper.paper_id, path, source, pagination_trusted, error)

    def save_status(self) -> None:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(self.status, indent=1), encoding="utf-8")
