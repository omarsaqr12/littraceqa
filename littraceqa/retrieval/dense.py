"""Dense bi-encoder retrieval over title+abstract, with a disk-cached matrix.

Runs entirely on the local GPU -- no API budget is spent on retrieval, which is
the only stage that must touch all 27,487 papers. Encoding the pool takes a few
minutes once; after that every query is a single matrix product.

Beyond query->paper search, the embedding matrix is what makes cluster expansion
possible (`expand.py`): the `multi_paper` gold sets are tight topical
neighbourhoods, and neighbourhoods are exactly what this matrix encodes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ..corpus import Paper, PaperPool
from ..textnorm import clean

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / "embeddings"

#: Default is a strong, small-enough-to-be-fast retrieval encoder. Swap via the
#: constructor -- the ablation harness treats this as a tunable.
DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"

#: BGE/E5-family models expect an instruction prefix on the *query* side only.
QUERY_PREFIXES = {
    "bge": "Represent this sentence for searching relevant passages: ",
    "e5": "query: ",
    "gte": "",
}


def _prefix_for(model_name: str) -> str:
    lowered = model_name.lower()
    for key, prefix in QUERY_PREFIXES.items():
        if key in lowered:
            return prefix
    return ""


def _doc_prefix_for(model_name: str) -> str:
    return "passage: " if "e5" in model_name.lower() else ""


class DenseRetriever:
    def __init__(
        self,
        pool: PaperPool,
        model_name: str = DEFAULT_MODEL,
        *,
        device: str | None = None,
        batch_size: int = 128,
        max_abstract_chars: int = 1200,
    ):
        self.pool = pool
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_abstract_chars = max_abstract_chars
        self._model = None
        self._device = device
        self.embeddings: np.ndarray | None = None

    # -- model / matrix -------------------------------------------------------

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self._device)
        return self._model

    def _doc_text(self, paper: Paper) -> str:
        return _doc_prefix_for(self.model_name) + (
            f"{clean(paper.title)}. {clean(paper.abstract)[: self.max_abstract_chars]}"
        )

    def _cache_path(self) -> Path:
        signature = hashlib.sha1(
            f"{self.model_name}|{len(self.pool)}|{self.max_abstract_chars}".encode()
        ).hexdigest()[:16]
        return CACHE_DIR / f"pool_{signature}.npy"

    def build(self, refresh: bool = False, show_progress: bool = True) -> np.ndarray:
        path = self._cache_path()
        if path.exists() and not refresh:
            self.embeddings = np.load(path)
            return self.embeddings
        texts = [self._doc_text(p) for p in self.pool.papers]
        matrix = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        ).astype(np.float32)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(path, matrix)
        self.embeddings = matrix
        return matrix

    @property
    def matrix(self) -> np.ndarray:
        if self.embeddings is None:
            self.build()
        return self.embeddings  # type: ignore[return-value]

    # -- search ---------------------------------------------------------------

    def encode_query(self, query: str) -> np.ndarray:
        vector = self.model.encode(
            [_prefix_for(self.model_name) + query],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
        return vector.astype(np.float32)

    def search(
        self, query: str, top_k: int = 50, candidates: set[int] | None = None
    ) -> list[tuple[Paper, float]]:
        scores = self.matrix @ self.encode_query(query)
        if candidates is not None:
            mask = np.full(scores.shape, -np.inf, dtype=np.float32)
            index = np.fromiter(candidates, dtype=np.int64, count=len(candidates))
            mask[index] = scores[index]
            scores = mask
        top_k = min(top_k, len(scores))
        top = np.argpartition(-scores, top_k - 1)[:top_k]
        top = top[np.argsort(-scores[top])]
        return [(self.pool.papers[i], float(scores[i])) for i in top if np.isfinite(scores[i])]

    def neighbours(
        self,
        paper_ids: list[str],
        top_k: int = 20,
        candidates: set[int] | None = None,
        exclude_seeds: bool = True,
    ) -> list[tuple[Paper, float]]:
        """Nearest papers to a set of seeds, scored by max similarity to any seed.

        Max-similarity rather than centroid: a gold cluster can straddle two
        sub-topics, and averaging the seeds drifts into the space between them.
        """
        seed_indices = [self.pool.order[pid] for pid in paper_ids if pid in self.pool.order]
        if not seed_indices:
            return []
        scores = (self.matrix @ self.matrix[seed_indices].T).max(axis=1)
        if candidates is not None:
            mask = np.full(scores.shape, -np.inf, dtype=np.float32)
            index = np.fromiter(candidates, dtype=np.int64, count=len(candidates))
            mask[index] = scores[index]
            scores = mask
        if exclude_seeds:
            scores = scores.copy()
            scores[seed_indices] = -np.inf
        top_k = min(top_k, len(scores))
        top = np.argpartition(-scores, top_k - 1)[:top_k]
        top = top[np.argsort(-scores[top])]
        return [(self.pool.papers[i], float(scores[i])) for i in top if np.isfinite(scores[i])]
