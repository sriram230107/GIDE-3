"""Study Director and assessment planner: pure, explainable (every recommendation carries its reasons)."""
from __future__ import annotations
import random
from typing import Optional


def concept_priority(c: dict) -> float:
    """c: eff, risk, unlocks (# weak dependents), recent_wrong (0..1), prereq_weak (bool)."""
    score = (0.45 * (1 - c["eff"]) + 0.20 * c["risk"]
             + 0.20 * min(1.0, c.get("unlocks", 0) / 3.0) + 0.15 * c.get("recent_wrong", 0.0))
    if c.get("prereq_weak"):
        score *= 0.6  # study the weak prerequisite first
    return score


def build_reasons(c: dict, prereq_names: list[str], dependents: list[str]) -> list[str]:
    r = [f"Estimated mastery {c['eff']*100:.0f}%"]
    if c["risk"] >= 0.4:
        r.append(f"Forgetting risk {'high' if c['risk'] >= 0.6 else 'medium'} ({c['risk']*100:.0f}%)")
    if c.get("last_wrong_days") is not None and c["last_wrong_days"] <= 7:
        r.append(f"Last incorrect attempt {c['last_wrong_days']:.0f} day(s) ago")
    if dependents:
        r.append("Prerequisite for: " + ", ".join(dependents[:3]))
    if prereq_names:
        r.append("Build on first: " + ", ".join(prereq_names[:3]))
    if c.get("attempts", 0) == 0:
        r.append("Not practised yet")
    return r


def study_plan(concepts: list[dict], minutes: int = 30) -> list[dict]:
    """concepts: [{id,name,eff,risk,attempts,prereq_ids,dependent_ids,last_wrong_days,topic}].
    Returns activity blocks that fill `minutes`, each with reasons derived from the numbers."""
    by_id = {c["id"]: c for c in concepts}
    enriched = []
    for c in concepts:
        weak_pre = [p for p in c.get("prereq_ids", []) if p in by_id and by_id[p]["eff"] < 0.5]
        weak_dep = [d for d in c.get("dependent_ids", []) if d in by_id and by_id[d]["eff"] < 0.6]
        lw = c.get("last_wrong_days")
        e = {**c, "unlocks": len(weak_dep), "prereq_weak": bool(weak_pre),
             "recent_wrong": 1.0 if (lw is not None and lw <= 3) else (0.5 if (lw is not None and lw <= 7) else 0.0)}
        e["score"] = concept_priority(e)
        e["_pre"] = [by_id[p]["name"] for p in weak_pre]
        e["_dep"] = [by_id[d]["name"] for d in weak_dep]
        enriched.append(e)
    candidates = [e for e in enriched if not (e["eff"] >= 0.9 and e["risk"] < 0.3)]
    candidates.sort(key=lambda e: e["score"], reverse=True)

    plan, left = [], minutes
    for e in candidates:
        if left < 5:
            break
        if e["eff"] < 0.5 or e["attempts"] == 0:
            blocks = [("Review concept in sources", 8), ("Targeted practice", 6)]
        elif e["risk"] >= 0.5:
            blocks = [("Quick revision", 5), ("Adaptive quiz", 6)]
        else:
            blocks = [("Adaptive quiz", 7)]
        for label, m in blocks:
            if left < m:
                continue
            plan.append({"concept_id": e["id"], "concept": e["name"], "activity": label, "minutes": m,
                         "reasons": build_reasons(e, e["_pre"], e["_dep"])})
            left -= m
        if len(plan) >= 6:
            break
    return plan


def exam_plan(concepts: list[dict], exam_date: str, minutes_per_day: int, today: Optional[str] = None) -> list[dict]:
    """Multi-day plan: exam_date + minutes/day -> per-day blocks reusing study_plan.

    concepts: same shape as study_plan input. exam_date/today: YYYY-MM-DD.
    Days run from today to exam_date inclusive, capped at 60. Weakest concepts
    are scheduled first: each day takes the next slice of priority-ordered
    concepts that fits minutes_per_day. Pure function (no DB, no network).
    """
    from datetime import date
    exam = date.fromisoformat(exam_date)
    now = date.fromisoformat(today) if today else date.today()
    if exam < now:
        raise ValueError("exam_date is in the past")
    n_days = min((exam - now).days + 1, 60)
    if not concepts or minutes_per_day < 5:
        return [{"date": str(now), "minutes": 0, "blocks": []}] if n_days else []
    ordered = sorted(concepts, key=concept_priority, reverse=True)
    days, idx = [], 0
    for d in range(n_days):
        day = now.fromordinal(now.toordinal() + d)
        # rotate through weakest-first so every day has material; stop repeating mastered ones
        todo = ordered[idx:] + ordered[:idx]
        blocks = study_plan(todo, minutes_per_day)
        days.append({"date": str(day), "minutes": sum(b["minutes"] for b in blocks), "blocks": blocks})
        if blocks:
            idx = (idx + 1) % len(ordered)
    return days


def weak_concepts(concepts: list[dict], threshold: float = 0.6) -> list[dict]:
    """Concepts needing practice: eff below threshold (unseen concepts count as weak).

    Same 0.6 cut as the assessment report's weak rule. Pure function.
    """
    return sorted([c for c in concepts if c.get("eff", 0.0) < threshold],
                  key=lambda c: c.get("eff", 0.0))


# ----------------------------- assessment planning --------------------------
def target_difficulty(eff_mastery: float, mode: str) -> float:
    if mode == "easy":
        return 1.5
    if mode == "hard":
        return 4.5
    return round(1.0 + 4.0 * max(0.0, min(1.0, eff_mastery)), 1)  # adaptive


def plan_assessment(concepts: list[dict], n: int, focus: str = "weak", difficulty: str = "adaptive",
                    qtypes: Optional[list[str]] = None, rng: Optional[random.Random] = None) -> list[dict]:
    """concepts: [{id, eff, importance}] within the chosen scope. Returns n slots
    [{concept_id, qtype, target_difficulty}]. focus: weak | balanced | exam."""
    rng = rng or random.Random()
    qtypes = qtypes or ["mcq"]
    if not concepts or n <= 0:
        return []
    if focus == "weak":
        w = [(1.0 - c["eff"]) + 0.1 for c in concepts]
    elif focus == "exam":
        w = [max(c.get("importance", 1.0), 0.1) for c in concepts]
    else:
        w = [1.0 for _ in concepts]
    total = sum(w)
    # largest-remainder allocation so counts are deterministic given weights
    raw = [n * x / total for x in w]
    counts = [int(r) for r in raw]
    rem = n - sum(counts)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[:rem]:
        counts[i] += 1
    slots = []
    for c, k in zip(concepts, counts):
        for _ in range(k):
            slots.append({"concept_id": c["id"], "target_difficulty": target_difficulty(c["eff"], difficulty)})
    rng.shuffle(slots)
    for i, s in enumerate(slots):
        s["qtype"] = qtypes[i % len(qtypes)]
    return slots
