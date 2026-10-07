from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm
from app.auth.deps import current_user
from app.core.database import get_db
from app.database.models import EvalRun

router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(current_user)])


@router.get("/eval/runs")
async def runs(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(50))).scalars().all()
    return [{"id": str(r.id), "kind": r.kind, "config": r.config, "metrics": r.metrics, "notes": r.notes,
             "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/system/models")
async def models():
    """Lists the models available per capability."""
    try:
        return {"models": llm.get_status()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, str(e))
