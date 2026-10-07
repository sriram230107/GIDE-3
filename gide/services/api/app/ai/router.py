from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm, tutor
from app.auth.deps import current_user
from app.core.database import get_db
from app.database.models import Conversation, Message, User
from app.learner.service import apply_evidence

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


class Ask(BaseModel):
    course_id: UUID
    question: str
    conversation_id: Optional[UUID] = None
    level: str = "current"            # beginner | current | exam | expert
    mode: str = "course_only"         # course_only | general


class Check(BaseModel):
    course_id: UUID
    concept_id: UUID
    question: str
    student_answer: str
    chunk_ids: list[str]


def _llm_guard():
    if not llm.available():
        raise HTTPException(503, "GEMINI_API_KEY is not configured on the server")


@router.post("/ask")
async def ask(p: Ask, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    _llm_guard()
    if not p.question.strip():
        raise HTTPException(400, "Empty question")
    conv = await db.get(Conversation, p.conversation_id) if p.conversation_id else None
    if conv is None:
        conv = Conversation(user_id=user.id, course_id=p.course_id)
        db.add(conv)
        await db.flush()
    elif conv.user_id != user.id:
        raise HTTPException(403, "Not your conversation")
    hist = [{"role": m.role, "content": m.content} for m in (await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at))).scalars()]
    try:
        res = await tutor.answer(db, user.id, p.course_id, p.question, p.level, p.mode, hist)
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(502, f"Tutor failed: {e}")
    db.add(Message(conversation_id=conv.id, role="user", content=p.question))
    db.add(Message(conversation_id=conv.id, role="assistant", content=res["answer"], label=res["label"],
                   citations=res["citations"], meta={k: res[k] for k in ("top_dense", "gate", "level", "primary_concept")}))
    # weak evidence: logged as 'question' (weight 0 in mastery until validated by simulation)
    if res.get("primary_concept_id") and res["label"] in ("GROUNDED", "PARTIAL"):
        await apply_evidence(db, user.id, UUID(res["primary_concept_id"]), "question", None, meta={"q": p.question[:200]})
    await db.commit()
    return {**res, "conversation_id": str(conv.id)}


@router.post("/check")
async def check(p: Check, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    _llm_guard()
    res = await tutor.judge_check(db, p.question, p.student_answer, p.chunk_ids)
    ev = await apply_evidence(db, user.id, p.concept_id, "check", res["correct"], "short", 3.0, None, {"q": p.question[:200]})
    await db.commit()
    return {**res, "mastery": {"before": round(ev["p_before"], 3), "after": round(ev["p_after"], 3)}}


@router.get("/conversations/{conversation_id}")
async def get_conv(conversation_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "Not found")
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at))).scalars().all()
    return [{"role": m.role, "content": m.content, "label": m.label, "citations": m.citations} for m in msgs]
