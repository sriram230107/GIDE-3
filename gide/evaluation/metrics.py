"""Pure evaluation metrics (unit-tested). No DB, no network."""
from __future__ import annotations
from typing import Optional

TIME_TOL_S = 5.0


def location_matches(expected: dict, got: dict, time_tol: float = TIME_TOL_S) -> bool:
    """expected: {source: 'substring of title', page|slide|t_start,t_end}; got: a citation dict."""
    src = (expected.get("source") or "").lower()
    if src and src not in (got.get("source_title") or "").lower():
        return False
    if expected.get("page") is not None:
        return got.get("page") == expected["page"]
    if expected.get("slide") is not None:
        return got.get("slide") == expected["slide"]
    if expected.get("t_start") is not None:
        gs = got.get("time_start")
        if gs is None:
            return False
        ge = got.get("time_end") if got.get("time_end") is not None else gs
        es, ee = expected["t_start"], expected.get("t_end", expected["t_start"])
        return gs - time_tol <= ee and ge + time_tol >= es
    return True


def retrieval_metrics(results: list[list[dict]], expected: list[dict], ks=(1, 3, 5)) -> dict:
    """results[i] = ranked citation dicts for question i. Returns hit@k and MRR."""
    n = len(expected)
    if n == 0:
        return {}
    out = {}
    ranks = []
    for res, exp in zip(results, expected):
        r = next((i + 1 for i, c in enumerate(res) if location_matches(exp, c)), None)
        ranks.append(r)
    for k in ks:
        out[f"hit@{k}"] = round(sum(1 for r in ranks if r and r <= k) / n, 4)
    out["mrr"] = round(sum(1 / r for r in ranks if r) / n, 4)
    out["n"] = n
    return out


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = (2 * p * r / (p + r)) if p and r else None
    return {"precision": None if p is None else round(p, 4), "recall": None if r is None else round(r, 4),
            "f1": None if f is None else round(f, 4), "tp": tp, "fp": fp, "fn": fn}


def refusal_metrics(rows: list[dict]) -> dict:
    """rows: {expected: 'answer'|'partial'|'refuse', predicted_refuse: bool}.
    Positive class = refusal. Precision = of refusals, how many were right; recall = of off-material, how many refused."""
    tp = sum(1 for r in rows if r["expected"] == "refuse" and r["predicted_refuse"])
    fp = sum(1 for r in rows if r["expected"] != "refuse" and r["predicted_refuse"])
    fn = sum(1 for r in rows if r["expected"] == "refuse" and not r["predicted_refuse"])
    over_refusal_answerable = sum(1 for r in rows if r["expected"] == "answer" and r["predicted_refuse"])
    n_ans = sum(1 for r in rows if r["expected"] == "answer")
    return {**prf(tp, fp, fn), "answerable_over_refusal_rate": round(over_refusal_answerable / n_ans, 4) if n_ans else None}


def citation_accuracy(cited: list[list[dict]], expected: list[dict]) -> dict:
    """Of answers that cite something, how often does at least one citation point at the expected location."""
    answered = [(c, e) for c, e in zip(cited, expected) if c]
    if not answered:
        return {"citation_accuracy": None, "n_with_citations": 0}
    ok = sum(1 for c, e in answered if any(location_matches(e, x) for x in c))
    return {"citation_accuracy": round(ok / len(answered), 4), "n_with_citations": len(answered)}


def best_threshold(pos: list[float], neg: list[float]) -> Optional[dict]:
    """Choose dense_min separating answerable (pos) from off-material (neg) by max F1 for 'answerable'."""
    if not pos or not neg:
        return None
    cands = sorted(set(pos + neg))
    best = None
    for t in cands:
        tp = sum(1 for x in pos if x >= t)
        fp = sum(1 for x in neg if x >= t)
        fn = len(pos) - tp
        f = prf(tp, fp, fn)["f1"] or 0.0
        if best is None or f > best["f1"] or (f == best["f1"] and t > best["threshold"]):
            best = {"threshold": t, "f1": f, **prf(tp, fp, fn)}
    return best
