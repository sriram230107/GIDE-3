from __future__ import annotations
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import numpy as np
from sqlalchemy import select

from app.ai import llm
from app.assessment.generate import SkipQuestion, generate_question, grade_short, verify_question
from app.assessment.verify import grade_mcq, grade_numeric, is_duplicate, stem_hash
from app.database.models import (Assessment, AssessmentItem, Chunk, Concept, ContentUnit, GenerationAttempt, Question,
                                 Topic)
from app.learner import model as lm
from app.learner.director import plan_assessment
from app.learner.service import apply_evidence, course_overview, recommend
from app.retrieval.search import citation_for_unit

MAX_TRIES = 3


async def _attempted_question_ids(session, user_id: UUID) -> set[UUID]:
    rows = (await session.execute(select(AssessmentItem.question_id).join(Assessment, Assessment.id == AssessmentItem.assessment_id)
                                  .where(Assessment.user_id == user_id))).all()
    return {r[0] for r in rows}


async def _known_for_dedupe(session, course_id: UUID, concept_id: UUID):
    from app.core.config import settings
    active_model = settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL
    rows = (await session.execute(select(Question.stem, Question.stem_hash, Question.embedding, Question.embedding_model)
                                  .where(Question.course_id == course_id, Question.concept_id == concept_id))).all()
    if rows:
        for r in rows:
            if r[3] and r[3] != active_model:
                raise RuntimeError(f"rebuild required: question embedded with {r[3]} but active is {active_model}")
    hashes = {r[1] for r in rows}
    embs = np.asarray([r[2] for r in rows if r[2]], dtype=np.float32) if any(r[2] for r in rows) else None
    return [r[0] for r in rows], hashes, embs


async def _course_hashes(session, course_id: UUID) -> set[str]:
    return {r[0] for r in (await session.execute(select(Question.stem_hash).where(Question.course_id == course_id))).all()}


async def _generate_for(session, course_id: UUID, concept: Concept, qtype: str, target: float, used_chunks: set[UUID],
                        rng: random.Random) -> tuple[Optional[Question], list[str]]:
    reasons: list[str] = []
    chunks = (await session.execute(select(Chunk).where(Chunk.concept_id == concept.id))).scalars().all()
    chunks = [c for c in chunks if len(c.text) >= 120] or chunks
    if not chunks:
        return None, ["concept has no source chunks"]
    stems, hashes, embs = await _known_for_dedupe(session, course_id, concept.id)
    all_hashes = hashes | await _course_hashes(session, course_id)
    fresh = [c for c in chunks if c.id not in used_chunks] or chunks
    for attempt in range(MAX_TRIES):
        ch = rng.choice(fresh)
        t = qtype
        try:
            try:
                q = await generate_question(ch.text, t, target, stems)
            except SkipQuestion:
                if t == "numeric":  # nothing to compute here -> fall back to MCQ rather than failing the slot
                    t = "mcq"
                    q = await generate_question(ch.text, t, target, stems)
                else:
                    raise
            ver = await verify_question(q, ch.text)
            if not ver["ok"]:
                session.add(GenerationAttempt(course_id=course_id, passed=False, reason="; ".join(ver["issues"])[:500]))
                reasons.append("; ".join(ver["issues"]))
                continue
            emb = (await llm.aembed_texts([q["stem"]], "SEMANTIC_SIMILARITY"))[0]
            dup, why = is_duplicate(q["stem"], emb, all_hashes, embs)
            if dup:
                session.add(GenerationAttempt(course_id=course_id, passed=False, reason=f"duplicate: {why}"))
                reasons.append(f"duplicate: {why}")
                continue
            session.add(GenerationAttempt(course_id=course_id, passed=True))
            from app.core.config import settings
            active_model = settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL
            row = Question(course_id=course_id, chunk_id=ch.id, unit_id=ch.primary_unit_id, topic_id=concept.topic_id,
                           concept_id=concept.id, qtype=t, stem=q["stem"], options=q.get("options"), answer=q["answer"],
                           numeric_expr=q.get("numeric_expr"), tolerance=q.get("tolerance"), explanation=q["explanation"],
                           difficulty_prior=q["difficulty"], difficulty_est=q["difficulty"], verified=True,
                           verification=ver["report"], stem_hash=stem_hash(q["stem"]), embedding=[float(x) for x in emb],
                           embedding_model=active_model)
            session.add(row)
            await session.flush()
            used_chunks.add(ch.id)
            return row, reasons
        except Exception as e:  # noqa: BLE001 - recorded in the shortfall report
            session.add(GenerationAttempt(course_id=course_id, passed=False, reason=f"error: {str(e)[:300]}"))
            reasons.append(f"error: {str(e)[:200]}")
    return None, reasons


async def _from_pool(session, course_id: UUID, concept_id: UUID, qtype: str, target: float, attempted: set[UUID],
                     chosen: set[UUID]) -> Optional[Question]:
    pool = (await session.execute(select(Question).where(Question.course_id == course_id, Question.concept_id == concept_id,
                                                         Question.qtype == qtype, Question.verified.is_(True)))).scalars().all()
    pool = [q for q in pool if q.id not in attempted and q.id not in chosen and abs(q.difficulty_est - target) <= 1.5]
    return min(pool, key=lambda q: abs(q.difficulty_est - target)) if pool else None


def _public_item(item: AssessmentItem, q: Question, topic: Optional[str], concept: Optional[str]) -> dict[str, Any]:
    opts = None
    if q.qtype == "mcq":
        opts = [q.options[i]["text"] for i in item.option_order]
    return {"item_id": str(item.id), "position": item.position, "qtype": q.qtype, "stem": q.stem, "options": opts,
            "tags": {"topic": topic, "concept": concept, "difficulty": round(q.difficulty_est, 1),
                     "unit_id": str(q.unit_id) if q.unit_id else None}}


async def create_assessment(session, user_id: UUID, course_id: UUID, cfg: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random()
    kind = cfg.get("kind", "quiz")
    n = max(1, min(int(cfg.get("n", 8)), 20))
    ov = await course_overview(session, user_id, course_id)
    chunk_counts: dict[str, int] = defaultdict(int)
    for cid, in (await session.execute(select(Chunk.concept_id).where(Chunk.course_id == course_id, Chunk.concept_id.is_not(None)))).all():
        chunk_counts[str(cid)] += 1
    scope_topics, scope_concepts = set(cfg.get("topic_ids") or []), set(cfg.get("concept_ids") or [])
    pool = [c for c in ov["concepts"] if chunk_counts.get(c["id"])
            and (not scope_topics or c["topic_id"] in scope_topics) and (not scope_concepts or c["id"] in scope_concepts)]
    if not pool:
        raise ValueError("no concepts with source material in this scope (build the knowledge base first)")
    for c in pool:
        c["importance"] = chunk_counts[c["id"]]

    if kind == "diagnostic":
        by_topic: dict[str, list[dict]] = defaultdict(list)
        for c in pool:
            by_topic[c["topic_id"]].append(c)
        pool = [c for cs in by_topic.values() for c in sorted(cs, key=lambda x: -x["importance"])[:2]]
        n, focus, difficulty = min(max(len(pool), 4), 12), "balanced", "adaptive"
        pool = pool[:n]
    else:
        focus, difficulty = cfg.get("focus", "weak"), cfg.get("difficulty", "adaptive")
    slots = plan_assessment(pool, n, focus, difficulty, cfg.get("qtypes") or ["mcq"], rng)

    attempted = await _attempted_question_ids(session, user_id)
    chosen: set[UUID] = set()
    used_chunks: set[UUID] = set()
    assess = Assessment(user_id=user_id, course_id=course_id, kind=kind, config=cfg)
    session.add(assess)
    await session.flush()
    concept_cache: dict[str, Concept] = {}
    shortfalls: list[dict] = []
    items_out: list[dict] = []
    pos = 0
    for slot in slots:
        cid = slot["concept_id"]
        concept = concept_cache.get(cid) or (await session.execute(select(Concept).where(Concept.id == UUID(cid)))).scalar_one()
        concept_cache[cid] = concept
        q = await _from_pool(session, course_id, concept.id, slot["qtype"], slot["target_difficulty"], attempted, chosen)
        if q is None:
            q, reasons = await _generate_for(session, course_id, concept, slot["qtype"], slot["target_difficulty"], used_chunks, rng)
            if q is None:
                shortfalls.append({"concept": concept.name, "reasons": reasons[-3:]})
                continue
        chosen.add(q.id)
        order = list(range(len(q.options))) if q.qtype == "mcq" else None
        if order:
            rng.shuffle(order)
        item = AssessmentItem(assessment_id=assess.id, question_id=q.id, position=pos, option_order=order)
        session.add(item)
        await session.flush()
        topic_name = (await session.execute(select(Topic.name).where(Topic.id == q.topic_id))).scalar_one_or_none()
        items_out.append(_public_item(item, q, topic_name, concept.name))
        pos += 1
    if not items_out:
        await session.rollback()
        raise RuntimeError(f"could not produce any verified question: {shortfalls}")
    await session.commit()
    return {"assessment_id": str(assess.id), "kind": kind, "requested": n, "items": items_out, "shortfall": shortfalls}


async def answer_item(session, user_id: UUID, item_id: UUID, answer: str, response_time: Optional[float]) -> dict[str, Any]:
    item = (await session.execute(select(AssessmentItem).where(AssessmentItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise LookupError("item not found")
    assess = (await session.execute(select(Assessment).where(Assessment.id == item.assessment_id))).scalar_one()
    if assess.user_id != user_id:
        raise PermissionError("not your assessment")
    if item.answered_at is not None:
        raise ValueError("item already answered")
    q = (await session.execute(select(Question).where(Question.id == item.question_id))).scalar_one()
    chunk = (await session.execute(select(Chunk).where(Chunk.id == q.chunk_id))).scalar_one_or_none() if q.chunk_id else None

    misconception: Optional[str] = None
    extra_feedback = ""
    if q.qtype == "mcq":
        pos = int(answer)
        if not (0 <= pos < len(item.option_order)):
            raise ValueError("invalid option")
        correct, misconception = grade_mcq(q.options, item.option_order, pos)
        shown = q.options[item.option_order[pos]]["text"]
    elif q.qtype == "numeric":
        correct, shown = grade_numeric(answer, q.answer, q.tolerance), answer
    else:
        g = await grade_short(q.stem, q.answer, answer, chunk.text if chunk else "")
        correct, shown, extra_feedback = g["correct"], answer, g["feedback"]

    now = datetime.now(timezone.utc)
    item.user_answer, item.correct, item.response_time, item.answered_at = shown, correct, response_time, now
    q.attempts += 1
    q.correct_count += 1 if correct else 0
    q.difficulty_est = lm.update_difficulty(q.difficulty_prior, q.attempts, q.correct_count)
    ev = None
    if q.concept_id:
        ev = await apply_evidence(session, user_id, q.concept_id, "quiz", correct, q.qtype, q.difficulty_est, response_time,
                                  {"question_id": str(q.id), "assessment_id": str(assess.id), "misconception": misconception})
    cit = await citation_for_unit(session, q.unit_id, 1, chunk.text[:240] if chunk else "") if q.unit_id else None
    fb = {"correct": correct, "your_answer": shown, "correct_answer": q.answer, "explanation": q.explanation,
          "grader_note": extra_feedback or None, "misconception": misconception, "citation": cit,
          "mastery": ({"before": round(ev["p_before"], 3), "after": round(ev["p_after"], 3)} if ev else None)}
    item.feedback = fb
    remaining = (await session.execute(select(AssessmentItem).where(AssessmentItem.assessment_id == assess.id,
                                                                     AssessmentItem.answered_at.is_(None)))).scalars().all()
    if not remaining:
        assess.status, assess.completed_at = "completed", now
    await session.commit()
    return {**fb, "assessment_completed": not remaining}


async def report(session, user_id: UUID, assessment_id: UUID) -> dict[str, Any]:
    assess = (await session.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one_or_none()
    if not assess or assess.user_id != user_id:
        raise LookupError("assessment not found")
    items = (await session.execute(select(AssessmentItem).where(AssessmentItem.assessment_id == assessment_id)
                                   .order_by(AssessmentItem.position))).scalars().all()
    answered = [i for i in items if i.answered_at]
    qs = {q.id: q for q in (await session.execute(select(Question).where(Question.id.in_([i.question_id for i in items])))).scalars()}
    per_concept: dict[UUID, dict] = defaultdict(lambda: {"n": 0, "correct": 0})
    miscon: dict[tuple, dict] = {}
    for i in answered:
        q = qs[i.question_id]
        d = per_concept[q.concept_id]
        d["n"] += 1
        d["correct"] += 1 if i.correct else 0
        m = (i.feedback or {}).get("misconception")
        if m:
            e = miscon.setdefault((q.concept_id, m), {"misconception": m, "count": 0, "citation": (i.feedback or {}).get("citation")})
            e["count"] += 1
    names = {c.id: c.name for c in (await session.execute(select(Concept).where(Concept.id.in_([k for k in per_concept if k])))).scalars()} if per_concept else {}
    ov = await course_overview(session, user_id, assess.course_id)
    mast = {c["id"]: c for c in ov["concepts"]}
    rows = []
    for cid, d in per_concept.items():
        acc = d["correct"] / d["n"]
        mm = mast.get(str(cid), {})
        rows.append({"concept_id": str(cid), "concept": names.get(cid, "?"), "answered": d["n"], "correct": d["correct"],
                     "accuracy": round(acc, 3), "mastery_now": mm.get("eff"), "weak": acc < 0.6 or (mm.get("eff") or 1) < 0.5})
    rows.sort(key=lambda r: r["accuracy"])
    times = [i.response_time for i in answered if i.response_time]
    rec = await recommend(session, user_id, assess.course_id, 20)
    return {"assessment_id": str(assessment_id), "status": assess.status, "answered": len(answered), "total": len(items),
            "score": round(sum(1 for i in answered if i.correct) / len(answered), 3) if answered else None,
            "avg_response_time_s": round(sum(times) / len(times), 1) if times else None, "by_concept": rows,
            "weak_concepts": [r for r in rows if r["weak"]],
            "likely_misconceptions": sorted(({**v, "concept": names.get(k[0], "?")} for k, v in miscon.items()), key=lambda x: -x["count"]),
            "next_steps": rec["plan"][:3]}
