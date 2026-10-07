"""Learner model: pure functions, no I/O (so it is unit-testable and reused by the simulator).

Mastery = Bayesian-Knowledge-Tracing-style posterior with evidence weighting:
  quiz     (verified assessment answer)       strong
  check    (tutor check-for-understanding)    medium
  question (student merely asked something)   logged, weight 0 until validated in simulation

Forgetting is a separate heuristic layer (exponential retrievability with growing stability).
Response time is logged elsewhere but NOT used here.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

EVIDENCE_WEIGHTS = {"quiz": 1.0, "check": 0.5, "question": 0.0, "intake": 0.0}

P_INIT = 0.20
P_TRANSIT = 0.15
GUESS_BASE = {"mcq": 0.25, "short": 0.08, "numeric": 0.05}
STABILITY_INIT = 2.0
STABILITY_MAX = 120.0


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def item_params(qtype: str, difficulty: float) -> tuple[float, float]:
    """(guess, slip) for an item. Harder items: lower guess, higher slip."""
    d = clip((difficulty - 1.0) / 4.0, 0.0, 1.0)
    g0 = GUESS_BASE.get(qtype, 0.15)
    guess = clip(g0 * (1.2 - 0.4 * d), 0.01, 0.5)
    slip = 0.05 + 0.16 * d
    return guess, slip


def bkt_posterior(p: float, correct: bool, guess: float, slip: float) -> float:
    if correct:
        num = p * (1 - slip)
        den = num + (1 - p) * guess
    else:
        num = p * slip
        den = num + (1 - p) * (1 - guess)
    return num / den if den > 0 else p


def update_mastery(p: float, correct: Optional[bool], kind: str, qtype: str = "mcq",
                   difficulty: float = 3.0, p_transit: float = P_TRANSIT) -> float:
    """Return the new P(mastery). Evidence with weight 0 (or correct is None) leaves p unchanged."""
    w = EVIDENCE_WEIGHTS.get(kind, 0.0)
    if w <= 0.0 or correct is None:
        return p
    guess, slip = item_params(qtype, difficulty)
    post = bkt_posterior(p, correct, guess, slip)
    blended = p + w * (post - p)
    learned = blended + (1 - blended) * p_transit * w  # opportunity to learn (feedback shown)
    return clip(learned, 0.01, 0.99)


# ------------------------------- forgetting ---------------------------------
def retrievability(days_since: float, stability_days: float) -> float:
    if days_since <= 0:
        return 1.0
    return math.exp(-days_since / max(stability_days, 0.1))


def update_stability(stability: float, correct: Optional[bool], kind: str) -> float:
    if correct is None or EVIDENCE_WEIGHTS.get(kind, 0.0) <= 0:
        return stability
    if correct:
        return min(STABILITY_MAX, stability * (1.8 if kind == "quiz" else 1.4))
    return max(1.0, stability * 0.6)


def effective_mastery(p: float, days_since: Optional[float], stability: float) -> float:
    """Mastery discounted by forgetting. Never-practised concepts keep their prior as is."""
    if days_since is None:
        return p
    r = retrievability(days_since, stability)
    return p * (0.5 + 0.5 * r)


def forgetting_risk(days_since: Optional[float], stability: float) -> float:
    if days_since is None:
        return 0.0
    return 1.0 - retrievability(days_since, stability)


def days_between(then: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
    if then is None:
        return None
    now = now or datetime.now(timezone.utc)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (now - then).total_seconds() / 86400.0)


# ---------------------------- cold start priors -----------------------------
INTAKE_PRIORS = {"new": 0.10, "some": 0.35, "comfortable": 0.60}


def intake_prior(level: str) -> float:
    return INTAKE_PRIORS.get(level, P_INIT)


# ------------------------------ item difficulty -----------------------------
def update_difficulty(prior: float, attempts: int, correct: int, k: float = 4.0) -> float:
    """Blend the LLM difficulty guess (1..5) with observed error rate (shrinkage toward prior)."""
    prior_err = clip((prior - 1.0) / 4.0, 0.0, 1.0)
    wrong = max(0, attempts - correct)
    est_err = (k * prior_err + wrong) / (k + attempts)
    return 1.0 + 4.0 * est_err


# ------------------------------ topic rollup --------------------------------
def rollup(values: list[float], weights: Optional[list[float]] = None) -> float:
    if not values:
        return 0.0
    if not weights:
        return sum(values) / len(values)
    tw = sum(weights)
    return sum(v * w for v, w in zip(values, weights)) / tw if tw else sum(values) / len(values)
