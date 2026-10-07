"""Arq worker functions. Blocking parsers run in threads (asyncio.to_thread) so the event loop never blocks.
Each job updates ITS OWN ProcessingJob row; failures are recorded with stage + error (never swallowed)."""
import asyncio
import traceback
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.queue import redis_settings
from app.core.storage import get_storage_path
from app.database.models import ContentUnit, ProcessingJob, Source


async def _latest_job(session, source_id: UUID) -> ProcessingJob:
    res = await session.execute(select(ProcessingJob).where(ProcessingJob.source_id == source_id)
                                .order_by(ProcessingJob.created_at.desc()).limit(1))
    job = res.scalar_one_or_none()
    if job is None:
        job = ProcessingJob(source_id=source_id)
        session.add(job)
        await session.flush()
    return job


async def _stage(session, job: ProcessingJob, source: Source, stage: str, pct: int, state: str = "processing"):
    job.state, job.stage, job.progress_percent = state, stage, pct
    source.status = state if state in ("processing", "completed", "failed") else source.status
    await session.commit()


def _parse(source: Source, storage) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Blocking. Returns (unit dicts, metadata)."""
    t = source.source_type
    if t == "pdf":
        from app.ingestion.pdf_parser import extract_pdf_pages
        units = extract_pdf_pages(source.file_path, source.id)
        pages = {u["page_number"] for u in units if u.get("page_number")}
        return units, {"page_count": len(pages), "warnings": []}
    if t == "pptx":
        from app.ingestion.pptx_parser import extract_pptx
        return extract_pptx(source.file_path, source.id, storage)
    if t == "video":
        from app.ingestion.video_parser import extract_video
        return extract_video(source.file_path, source.id, storage, settings.WHISPER_MODEL,
                             settings.KEYFRAME_THRESHOLD, settings.KEYFRAME_MAX_GAP_S, settings.KEYFRAME_MAX_COUNT)
    if t == "image":
        from app.ingestion.image_parser import extract_image
        return extract_image(source.file_path, source.id, storage), {"warnings": []}
    raise ValueError(f"unsupported source type {t!r}")


async def ingest_source(ctx, source_id_str: str):
    from app.ingestion.vision import run_vision
    source_id = UUID(source_id_str)
    async with AsyncSessionLocal() as session:
        source = (await session.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
        if not source:
            print(f"[Worker] Source {source_id} not found")
            return
        job = await _latest_job(session, source_id)
        try:
            await _stage(session, job, source, f"parsing_{source.source_type}", 15)
            storage = get_storage_path()
            await session.execute(delete(ContentUnit).where(ContentUnit.source_id == source_id))  # idempotent retry
            units, meta = await asyncio.to_thread(_parse, source, storage)

            await _stage(session, job, source, "storing_units", 55)
            session.add_all([ContentUnit(**u) for u in units])
            await session.flush()

            await _stage(session, job, source, "generating_vision_captions", 70)
            vstats = await run_vision(session, source_id)

            warnings = list(meta.get("warnings", []))
            if vstats.get("vision_skipped_reason"):
                warnings.append(f"vision/OCR skipped: {vstats['vision_skipped_reason']}")
            if vstats.get("vision_failed"):
                warnings.append(f"{vstats['vision_failed']} image(s) failed vision/OCR (see unit metadata.vision_error)")
            if vstats.get("vision_capped_at"):
                warnings.append(f"vision capped at {vstats['vision_capped_at']} of {vstats['vision_candidates']} images")
            source.source_metadata = {**source.source_metadata, **meta, **vstats, "unit_count": len(units),
                                      "warnings": warnings}
            source.error_message = None
            await _stage(session, job, source, "done", 100, state="completed")
            print(f"[Worker] Ingested {len(units)} units for {source.title} ({source.id}); warnings={warnings}")
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            print(f"[Worker] Ingestion failed for {source_id}: {e}\n{tb}")
            await session.rollback()
            source = (await session.execute(select(Source).where(Source.id == source_id))).scalar_one()
            job = await _latest_job(session, source_id)
            failed_stage = job.stage
            source.status, source.error_message = "failed", f"[{failed_stage}] {e}"
            job.state, job.stage = "failed", failed_stage
            job.error_detail = {"error": str(e), "stage": failed_stage, "traceback": tb}
            await session.commit()


# Backwards-compatible name used by the Step 0 tests
process_pdf_source = ingest_source


async def build_knowledge_job(ctx, course_id_str: str):
    from app.knowledge.builder import build_knowledge
    await build_knowledge(UUID(course_id_str))


class WorkerSettings:
    functions = [ingest_source, build_knowledge_job]
    redis_settings = redis_settings()
    max_jobs = 2
    job_timeout = 60 * 60 * 3
    keep_result = 3600
