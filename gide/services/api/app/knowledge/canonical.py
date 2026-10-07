"""Pure helpers for concept canonicalisation and a cycle-free prerequisite graph."""
from __future__ import annotations
import re
import numpy as np

_STOP = {"the", "a", "an", "of", "and", "in", "to", "for", "on"}
_SUFFIX_WORDS = {"mechanism", "concept", "method", "technique", "algorithm", "process"}


def canonical_key(name: str) -> str:
    """'Self-Attention Mechanism' and 'self attention' -> 'self attention'."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s.replace("-", " "))
    words = [w for w in s.split() if w not in _STOP]
    if len(words) > 1 and words[-1] in _SUFFIX_WORDS:
        words = words[:-1]
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words]
    return " ".join(words)


def cluster_by_similarity(vectors: np.ndarray, threshold: float = 0.88) -> list[int]:
    """Greedy clustering on L2-normalised vectors. Returns a cluster id per row."""
    n = len(vectors)
    labels = [-1] * n
    reps: list[int] = []
    for i in range(n):
        best, best_s = -1, threshold
        for ci, r in enumerate(reps):
            s = float(vectors[i] @ vectors[r])
            if s >= best_s:
                best, best_s = ci, s
        if best == -1:
            reps.append(i)
            labels[i] = len(reps) - 1
        else:
            labels[i] = best
    return labels


def creates_cycle(edges: set[tuple[str, str]], concept: str, prereq: str) -> bool:
    """Edge means concept REQUIRES prereq. Adding it creates a cycle if prereq already (transitively) requires concept."""
    if concept == prereq:
        return True
    requires: dict[str, list[str]] = {}
    for c, p in edges:
        requires.setdefault(c, []).append(p)
    stack, seen = [prereq], set()
    while stack:
        cur = stack.pop()
        if cur == concept:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(requires.get(cur, []))
    return False


def add_edges_acyclic(candidates: list[tuple[str, str]], valid_ids: set[str]) -> tuple[set[tuple[str, str]], list[tuple[str, str]]]:
    """Return (accepted_edges, rejected_edges). Rejects unknown ids, self loops and cycle-creating edges."""
    accepted: set[tuple[str, str]] = set()
    rejected = []
    for c, p in candidates:
        if c not in valid_ids or p not in valid_ids or (c, p) in accepted or creates_cycle(accepted, c, p):
            rejected.append((c, p))
            continue
        accepted.add((c, p))
    return accepted, rejected


def topo_depths(ids: list[str], edges: set[tuple[str, str]]) -> dict[str, int]:
    """Depth = longest chain of prerequisites below a concept (0 = foundational)."""
    requires: dict[str, list[str]] = {i: [] for i in ids}
    for c, p in edges:
        requires.setdefault(c, []).append(p)
    memo: dict[str, int] = {}

    def depth(x: str, trail: frozenset = frozenset()) -> int:
        if x in memo:
            return memo[x]
        if x in trail:
            return 0
        d = 0
        for p in requires.get(x, []):
            d = max(d, depth(p, trail | {x}) + 1)
        memo[x] = d
        return d

    return {i: depth(i) for i in ids}
