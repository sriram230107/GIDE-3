from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm
from app.assessment import service
from app.auth.deps import current_user
from app.core.database import get_db
from app.database.models import User

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


class CreateAssessment(BaseModel):
    course_id: UUID
    kind: str = "quiz"                       # quiz | diagnostic | exam
    n: int = Field(8, ge=1, le=20)
    topic_ids: list[str] = []
    concept_ids: list[str] = []
    qtypes: list[str] = ["mcq"]              # mcq | short | numeric
    difficulty: str = "adaptive"             # easy | adaptive | hard
    focus: str = "weak"                      # weak | balanced | exam


class Answer(BaseModel):
    item_id: UUID
    answer: str
    response_time: Optional[float] = None


@router.post("")
async def create(p: CreateAssessment, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if not llm.available():
        raise HTTPException(503, "GEMINI_API_KEY is not configured on the server")
    bad = [t for t in p.qtypes if t not in ("mcq", "short", "numeric")]
    if bad:
        raise HTTPException(400, f"unknown question types {bad}")
    try:
        return await service.create_assessment(db, user.id, p.course_id, p.model_dump(mode="json"))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@router.post("/answer")
async def answer(p: Answer, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        return await service.answer_item(db, user.id, p.item_id, p.answer, p.response_time)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{assessment_id}/report")
async def report(assessment_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        return await service.report(db, user.id, assessment_id)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/stats/{course_id}")
async def stats(course_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    from sqlalchemy import func, select
    from app.assessment.verify import audit_error_rate
    from app.database.models import GenerationAttempt, Question
    total = (await db.execute(select(func.count(GenerationAttempt.id)).where(GenerationAttempt.course_id == course_id))).scalar_one()
    passed = (await db.execute(select(func.count(GenerationAttempt.id)).where(GenerationAttempt.course_id == course_id, GenerationAttempt.passed.is_(True)))).scalar_one()
    qn = (await db.execute(select(func.count(Question.id)).where(Question.course_id == course_id))).scalar_one()
    verifs = (await db.execute(select(Question.verification).where(Question.course_id == course_id))).scalars().all()
    audit = audit_error_rate([v.get("audit", {}).get("mark") for v in verifs if isinstance(v, dict) and isinstance(v.get("audit"), dict)])
    return {"generation_attempts": total, "passed_verification": passed,
            "verification_pass_rate": round(passed / total, 3) if total else None, "questions_in_bank": qn,
            "audit": audit}


class AuditMark(BaseModel):
    mark: str  # key_ok | key_wrong | unclear
    note: str = ""


@router.get("/questions")
async def list_questions(course_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Questions in the bank with their verification + audit state, for human review."""
    from sqlalchemy import select
    from app.database.models import Question
    qs = (await db.execute(select(Question).where(Question.course_id == course_id)
                           .order_by(Question.created_at.desc()).limit(200))).scalars().all()
    return {"questions": [{"id": str(q.id), "qtype": q.qtype, "stem": q.stem, "answer": q.answer,
                           "options": q.options, "explanation": q.explanation, "verified": q.verified,
                           "audit": (q.verification or {}).get("audit") if isinstance(q.verification, dict) else None,
                           "concept_id": str(q.concept_id) if q.concept_id else None} for q in qs]}


@router.post("/questions/{question_id}/audit")
async def audit_question(question_id: UUID, p: AuditMark, db: AsyncSession = Depends(get_db),
                         user: User = Depends(current_user)):
    """Record a human audit mark on a question's answer key (stored in verification.audit)."""
    from sqlalchemy import select
    from app.assessment.verify import AUDIT_MARKS
    from app.database.models import Question
    if p.mark not in AUDIT_MARKS:
        raise HTTPException(400, f"mark must be one of {list(AUDIT_MARKS)}")
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "question not found")
    ver = dict(q.verification or {})
    ver["audit"] = {"mark": p.mark, "note": p.note}
    q.verification = ver
    await db.commit()
    return {"id": str(q.id), "audit": ver["audit"]}
