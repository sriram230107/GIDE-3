from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.core.database import get_db
from app.core.queue import enqueue
from app.database.models import Chunk, Concept, ConceptPrereq, Source, Topic
from app.knowledge.canonical import topo_depths

router = APIRouter(prefix="/api/courses", tags=["knowledge"], dependencies=[Depends(current_user)])


@router.post("/{course_id}/build-knowledge")
async def build(course_id: UUID, db: AsyncSession = Depends(get_db)):
    n_ok = (await db.execute(select(func.count(Source.id)).where(Source.course_id == course_id, Source.status == "completed"))).scalar_one()
    n_busy = (await db.execute(select(func.count(Source.id)).where(Source.course_id == course_id, Source.status.in_(["queued", "processing"])))).scalar_one()
    if n_ok == 0:
        raise HTTPException(409, "No completed sources yet")
    if n_busy:
        raise HTTPException(409, f"{n_busy} source(s) still processing; wait for them to finish")
    try:
        await enqueue("build_knowledge_job", str(course_id))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Could not enqueue (is Redis running?): {e}")
    return {"queued": True, "warning": "Rebuilding resets learner mastery on this course's concepts."}


@router.get("/{course_id}/knowledge-status")
async def status(course_id: UUID, db: AsyncSession = Depends(get_db)):
    chunks = (await db.execute(select(func.count(Chunk.id)).where(Chunk.course_id == course_id))).scalar_one()
    tagged = (await db.execute(select(func.count(Chunk.id)).where(Chunk.course_id == course_id, Chunk.concept_id.is_not(None)))).scalar_one()
    topics = (await db.execute(select(func.count(Topic.id)).where(Topic.course_id == course_id))).scalar_one()
    concepts = (await db.execute(select(func.count(Concept.id)).where(Concept.course_id == course_id))).scalar_one()
    return {"chunks": chunks, "chunks_tagged": tagged, "topics": topics, "concepts": concepts, "ready": bool(chunks and concepts)}


@router.get("/{course_id}/graph")
async def graph(course_id: UUID, db: AsyncSession = Depends(get_db)):
    topics = (await db.execute(select(Topic).where(Topic.course_id == course_id).order_by(Topic.sequence))).scalars().all()
    concepts = (await db.execute(select(Concept).where(Concept.course_id == course_id))).scalars().all()
    ids = [c.id for c in concepts]
    edges = (await db.execute(select(ConceptPrereq).where(ConceptPrereq.concept_id.in_(ids)))).scalars().all() if ids else []
    counts = dict((await db.execute(select(Chunk.concept_id, func.count(Chunk.id)).where(Chunk.course_id == course_id).group_by(Chunk.concept_id))).all())
    e = {(str(x.concept_id), str(x.prereq_id)) for x in edges}
    depth = topo_depths([str(c.id) for c in concepts], e)
    return {"topics": [{"id": str(t.id), "name": t.name, "description": t.description} for t in topics],
            "concepts": [{"id": str(c.id), "name": c.name, "topic_id": str(c.topic_id) if c.topic_id else None,
                          "description": c.description, "aliases": c.aliases, "chunks": counts.get(c.id, 0),
                          "depth": depth[str(c.id)]} for c in concepts],
            "edges": [{"concept_id": a, "prereq_id": b} for a, b in sorted(e)]}


@router.get("/concepts/{concept_id}/sources")
async def concept_sources(concept_id: UUID, db: AsyncSession = Depends(get_db)):
    from app.retrieval.search import citation_for_unit
    rows = (await db.execute(select(Chunk).where(Chunk.concept_id == concept_id).limit(12))).scalars().all()
    return [await citation_for_unit(db, c.primary_unit_id, i + 1, c.text[:240]) for i, c in enumerate(rows)]
