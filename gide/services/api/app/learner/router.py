from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.core.database import get_db
from app.database.models import User
from app.learner import service

router = APIRouter(prefix="/api/learner", tags=["learner"])


class Intake(BaseModel):
    course_id: UUID
    levels: dict[str, str]  # topic_id -> new | some | comfortable


@router.get("/{course_id}/overview")
async def overview(course_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return await service.course_overview(db, user.id, course_id)


@router.get("/{course_id}/recommend")
async def recommend(course_id: UUID, minutes: int = 30, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return await service.recommend(db, user.id, course_id, max(5, min(minutes, 240)))


@router.get("/{course_id}/exam-plan")
async def exam_plan(course_id: UUID, exam_date: str, minutes_per_day: int = 30, db: AsyncSession = Depends(get_db),
                    user: User = Depends(current_user)):
    return await service.exam_schedule(db, user.id, course_id, exam_date, minutes_per_day)


@router.get("/{course_id}/flashcards")
async def flashcards(course_id: UUID, limit: int = 20, db: AsyncSession = Depends(get_db),
                     user: User = Depends(current_user)):
    return await service.flashcards(db, user.id, course_id, limit)


@router.post("/intake")
async def intake(p: Intake, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    n = await service.apply_intake(db, user.id, p.course_id, p.levels)
    await db.commit()
    return {"concepts_updated": n}
