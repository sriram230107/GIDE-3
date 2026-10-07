"""Pure retrieval math: dense top-k and reciprocal-rank fusion."""
from __future__ import annotations
import numpy as np


def normalize_rows(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def cosine_topk(matrix: np.ndarray, q: np.ndarray, k: int) -> list[tuple[int, float]]:
    """matrix rows and q must be L2-normalised. Returns [(row_index, cosine)] best first."""
    if matrix.size == 0:
        return []
    sims = matrix @ q
    k = min(k, len(sims))
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    return [(int(i), float(sims[i])) for i in idx]


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion over ranked id lists."""
    scores: dict[str, float] = {}
    for lst in rank_lists:
        for r, _id in enumerate(lst):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + r + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
