"""DB layer for the learner model (the math lives in learner/model.py)."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select

from app.database.models import Concept, ConceptPrereq, EvidenceEvent, Mastery, Question, Topic
from app.learner import model as lm
from app.learner.director import study_plan


def _now():
    return datetime.now(timezone.utc)


async def get_or_create(session, user_id: UUID, concept_id: UUID, prior: float = lm.P_INIT, source: str = "default") -> Mastery:
    m = (await session.execute(select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id == concept_id))).scalar_one_or_none()
    if m is None:
        m = Mastery(user_id=user_id, concept_id=concept_id, p_mastery=prior, stability_days=lm.STABILITY_INIT,
                    attempts=0, correct=0, streak=0, prior_source=source)
        session.add(m)
        await session.flush()
    return m


async def apply_evidence(session, user_id: UUID, concept_id: UUID, kind: str, correct: Optional[bool],
                         qtype: str = "mcq", difficulty: float = 3.0, response_time: Optional[float] = None,
                         meta: Optional[dict] = None) -> dict:
    """Update mastery from one piece of evidence and log it (every event is auditable)."""
    m = await get_or_create(session, user_id, concept_id)
    before = m.p_mastery
    now = _now()
    after = lm.update_mastery(before, correct, kind, qtype, difficulty)
    weight = lm.EVIDENCE_WEIGHTS.get(kind, 0.0)
    if weight > 0 and correct is not None:
        m.stability_days = lm.update_stability(m.stability_days, correct, kind)
        m.attempts += 1
        m.last_evidence_at = now
        if correct:
            m.correct += 1
            m.streak += 1
        else:
            m.streak = 0
            m.last_wrong_at = now
    m.p_mastery = after
    session.add(EvidenceEvent(user_id=user_id, concept_id=concept_id, kind=kind, weight=weight, correct=correct,
                              p_before=before, p_after=after, response_time=response_time, meta=meta or {}))
    await session.flush()
    return {"p_before": before, "p_after": after, "weight": weight}


async def course_overview(session, user_id: UUID, course_id: UUID) -> dict:
    concepts = (await session.execute(select(Concept).where(Concept.course_id == course_id))).scalars().all()
    topics = {t.id: t for t in (await session.execute(select(Topic).where(Topic.course_id == course_id).order_by(Topic.sequence))).scalars()}
    cids = [c.id for c in concepts]
    mast = {m.concept_id: m for m in (await session.execute(select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id.in_(cids)))).scalars()} if cids else {}
    edges = (await session.execute(select(ConceptPrereq).where(ConceptPrereq.concept_id.in_(cids)))).scalars().all() if cids else []
    week_ago = _now() - timedelta(days=7)
    old = {}
    if cids:
        rows = (await session.execute(
            select(EvidenceEvent.concept_id, func.min(EvidenceEvent.created_at)).where(
                EvidenceEvent.user_id == user_id, EvidenceEvent.concept_id.in_(cids), EvidenceEvent.weight > 0).group_by(EvidenceEvent.concept_id))).all()
        old = {r[0]: r[1] for r in rows}
    prereqs: dict[UUID, list[UUID]] = {}
    dependents: dict[UUID, list[UUID]] = {}
    for e in edges:
        prereqs.setdefault(e.concept_id, []).append(e.prereq_id)
        dependents.setdefault(e.prereq_id, []).append(e.concept_id)

    out = []
    for c in concepts:
        m = mast.get(c.id)
        p = m.p_mastery if m else lm.P_INIT
        days = lm.days_between(m.last_evidence_at) if m else None
        stab = m.stability_days if m else lm.STABILITY_INIT
        out.append({"id": str(c.id), "name": c.name, "topic_id": str(c.topic_id) if c.topic_id else None,
                    "topic": topics[c.topic_id].name if c.topic_id in topics else None,
                    "p": round(p, 4), "eff": round(lm.effective_mastery(p, days, stab), 4),
                    "risk": round(lm.forgetting_risk(days, stab), 4), "attempts": m.attempts if m else 0,
                    "correct": m.correct if m else 0, "practised": bool(m and m.attempts > 0),
                    "prior_source": m.prior_source if m else "default",
                    "last_wrong_days": lm.days_between(m.last_wrong_at) if m and m.last_wrong_at else None,
                    "prereq_ids": [str(x) for x in prereqs.get(c.id, [])],
                    "dependent_ids": [str(x) for x in dependents.get(c.id, [])]})
    by_topic: dict[str, list[dict]] = {}
    for c in out:
        by_topic.setdefault(c["topic_id"] or "none", []).append(c)
    topic_rows = [{"id": str(t.id), "name": t.name, "mastery": round(lm.rollup([c["eff"] for c in by_topic.get(str(t.id), [])]), 4),
                   "concepts": len(by_topic.get(str(t.id), [])), "practised": sum(1 for c in by_topic.get(str(t.id), []) if c["practised"])}
                  for t in topics.values()]
    practised = [c["eff"] for c in out if c["practised"]]
    return {"concepts": out, "topics": topic_rows,
            "overall": round(lm.rollup([c["eff"] for c in out]), 4) if out else 0.0,
            "overall_practised_only": round(lm.rollup(practised), 4) if practised else None,
            "concepts_practised": len(practised), "concepts_total": len(out)}


async def recommend(session, user_id: UUID, course_id: UUID, minutes: int) -> dict:
    ov = await course_overview(session, user_id, course_id)
    plan = study_plan(ov["concepts"], minutes)
    return {"minutes": minutes, "plan": plan, "total_minutes": sum(p["minutes"] for p in plan)}


async def exam_schedule(session, user_id: UUID, course_id: UUID, exam_date: str, minutes_per_day: int,
                      today: Optional[str] = None) -> dict:
    """Thin DB wrapper around director.exam_plan (pure logic stays in director)."""
    from app.learner.director import exam_plan
    ov = await course_overview(session, user_id, course_id)
    days = exam_plan(ov["concepts"], exam_date, max(5, min(minutes_per_day, 240)), today)
    return {"exam_date": exam_date, "minutes_per_day": minutes_per_day, "days": days,
            "total_minutes": sum(d["minutes"] for d in days)}


async def flashcards(session, user_id: UUID, course_id: UUID, limit: int = 20) -> dict:
    """Flashcards for weak concepts: verified short-answer Questions, each with a citation.

    Reuses verified Questions (qtype short) tied to a unit/chunk — the "verified
    answerable" guarantee is the assessment verify pipeline (verified=True).
    Citation comes from the question's own unit (citation_for_unit), i.e. the
    chunk it was generated from. No new tables, no new generation pipeline.
    """
    from app.learner.director import weak_concepts
    from app.retrieval.search import citation_for_unit
    ov = await course_overview(session, user_id, course_id)
    weak = weak_concepts(ov["concepts"])
    if not weak:
        return {"cards": []}
    wids = [UUID(c["id"]) for c in weak]
    qs = (await session.execute(
        select(Question).where(Question.course_id == course_id, Question.concept_id.in_(wids),
                               Question.qtype == "short", Question.verified.is_(True))
        .order_by(Question.concept_id))).scalars().all()
    names = {c["id"]: c["name"] for c in weak}
    cards = []
    for q in qs[:max(1, min(limit, 50))]:
        cit = await citation_for_unit(session, q.unit_id, 1, "") if q.unit_id else None
        cards.append({"question_id": str(q.id), "concept_id": str(q.concept_id),
                      "concept": names.get(str(q.concept_id), "?"), "front": q.stem,
                      "back": q.answer, "explanation": q.explanation, "citation": cit})
    return {"cards": cards}


async def apply_intake(session, user_id: UUID, course_id: UUID, levels: dict[str, str]) -> int:
    """levels: topic_id -> new|some|comfortable. Sets priors for concepts the student has not practised yet."""
    n = 0
    concepts = (await session.execute(select(Concept).where(Concept.course_id == course_id))).scalars().all()
    for c in concepts:
        lvl = levels.get(str(c.topic_id))
        if not lvl:
            continue
        m = await get_or_create(session, user_id, c.id)
        if m.attempts == 0:
            m.p_mastery, m.prior_source = lm.intake_prior(lvl), "intake"
            session.add(EvidenceEvent(user_id=user_id, concept_id=c.id, kind="intake", weight=0.0, correct=None,
                                      p_before=lm.P_INIT, p_after=m.p_mastery, meta={"level": lvl}))
            n += 1
    await session.flush()
    return n
