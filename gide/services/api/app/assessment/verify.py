"""Pure helpers for question verification, grading and novelty. No network, no DB."""
from __future__ import annotations
import ast
import hashlib
import math
import operator
import re
from typing import Any, Optional

import numpy as np

# ----------------------- safe arithmetic evaluator (no eval) ------------------
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10, "exp": math.exp,
          "sin": math.sin, "cos": math.cos, "tan": math.tan, "abs": abs, "round": round,
          "min": min, "max": max, "pow": pow}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expr: str) -> float:
    """Evaluate a numeric expression containing only numbers, + - * / ** %, parentheses, a few math functions."""
    tree = ast.parse(expr.strip(), mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            l, r = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(r) > 64:
                raise ValueError("exponent too large")
            return _BIN[type(n.op)](l, r)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UN:
            return _UN[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name) and n.id in _CONSTS:
            return _CONSTS[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"disallowed expression element: {type(n).__name__}")

    return float(ev(tree))


def numbers_close(a: float, b: float, tol: Optional[float]) -> bool:
    """tol is relative (e.g. 0.01 = 1%); absolute floor 1e-9 for values near zero."""
    t = 0.01 if tol is None else tol
    return abs(a - b) <= max(abs(b) * t, 1e-9)


def parse_number(s: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?|-?\.\d+", str(s))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


# -------------------------------- structure -----------------------------------
def check_structure(q: dict[str, Any]) -> list[str]:
    """Return a list of structural problems (empty list = OK)."""
    issues: list[str] = []
    if not (q.get("stem") or "").strip():
        issues.append("empty stem")
    if not (q.get("explanation") or "").strip():
        issues.append("empty explanation")
    t = q.get("qtype")
    if t == "mcq":
        opts = q.get("options") or []
        if len(opts) != 4:
            issues.append("mcq must have exactly 4 options")
        if sum(1 for o in opts if o.get("is_correct")) != 1:
            issues.append("mcq must have exactly one correct option")
        texts = [str(o.get("text", "")).strip().lower() for o in opts]
        if len(set(texts)) != len(texts) or "" in texts:
            issues.append("mcq options must be distinct and non-empty")
        for o in opts:
            if not o.get("is_correct") and not (o.get("misconception") or "").strip():
                issues.append("every distractor needs a misconception tag")
                break
    elif t == "numeric":
        expr = q.get("numeric_expr")
        ans = parse_number(q.get("answer", ""))
        if ans is None:
            issues.append("numeric answer is not a number")
        if not expr:
            issues.append("numeric question needs numeric_expr for code verification")
        elif ans is not None:
            try:
                val = safe_eval(expr)
                if not numbers_close(val, ans, q.get("tolerance")):
                    issues.append(f"numeric_expr evaluates to {val}, key says {ans}")
            except Exception as e:  # noqa: BLE001
                issues.append(f"numeric_expr failed: {e}")
    elif t == "short":
        if not (q.get("answer") or "").strip():
            issues.append("empty answer key")
    else:
        issues.append(f"unknown qtype {t!r}")
    return issues


# ----------------------------------- audit ------------------------------------
AUDIT_MARKS = ("key_ok", "key_wrong", "unclear")


def audit_error_rate(marks: list[str]) -> dict:
    """Audited answer-key error rate over human-reviewed questions.

    marks: per-question audit marks ('key_ok' | 'key_wrong' | 'unclear').
    'unclear' reviews are reported but excluded from the rate denominator.
    """
    decided = [m for m in marks if m in ("key_ok", "key_wrong")]
    wrong = sum(1 for m in decided if m == "key_wrong")
    return {"n_reviewed": len(marks), "n_decided": len(decided),
            "n_key_wrong": wrong,
            "audited_error_rate": round(wrong / len(decided), 4) if decided else None,
            "n_unclear": sum(1 for m in marks if m == "unclear")}


# ---------------------------------- novelty -----------------------------------
def stem_hash(stem: str) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()
    return hashlib.sha1(norm.encode()).hexdigest()


def is_duplicate(stem: str, emb: Optional[np.ndarray], known_hashes: set[str],
                 known_embs: Optional[np.ndarray], threshold: float = 0.90) -> tuple[bool, str]:
    if stem_hash(stem) in known_hashes:
        return True, "identical stem"
    if emb is not None and known_embs is not None and len(known_embs):
        sim = float(np.max(known_embs @ emb))
        if sim >= threshold:
            return True, f"near-duplicate (cosine {sim:.2f})"
    return False, ""


# ---------------------------------- grading -----------------------------------
def grade_mcq(question_options: list[dict], option_order: list[int], chosen_position: int) -> tuple[bool, Optional[str]]:
    """chosen_position indexes the SHUFFLED list shown to the student. Returns (correct, misconception)."""
    orig = option_order[chosen_position]
    opt = question_options[orig]
    return bool(opt.get("is_correct")), (None if opt.get("is_correct") else opt.get("misconception"))


def grade_numeric(user_answer: str, key_answer: str, tol: Optional[float]) -> bool:
    u, k = parse_number(user_answer), parse_number(key_answer)
    return u is not None and k is not None and numbers_close(u, k, tol)
