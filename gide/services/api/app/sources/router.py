import shutil
import uuid
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import current_user
from app.core.database import get_db
from app.core.queue import enqueue
from app.core.storage import get_storage_path, media_url_for, save_uploaded_source
from app.database.models import ContentUnit, Course, ProcessingJob, Source

router = APIRouter(prefix="/api", tags=["sources"], dependencies=[Depends(current_user)])

EXT_TYPES = {".pdf": ("pdf", "application/pdf"),
             ".pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
             ".mp4": ("video", "video/mp4"), ".webm": ("video", "video/webm"), ".mov": ("video", "video/quicktime"),
             ".mkv": ("video", "video/x-matroska"),
             ".png": ("image", "image/png"), ".jpg": ("image", "image/jpeg"), ".jpeg": ("image", "image/jpeg"),
             ".webp": ("image", "image/webp")}
MAX_BYTES = 2 * 1024 ** 3


class CourseCreate(BaseModel):
    title: str
    code: Optional[str] = None
    description: Optional[str] = None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    code: Optional[str] = None
    description: Optional[str] = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    state: str
    stage: str
    progress_percent: int
    attempt_number: int
    error_detail: Optional[dict] = None


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    course_id: UUID
    title: str
    source_type: str
    file_size_bytes: int
    status: str
    error_message: Optional[str] = None
    source_metadata: dict
    processing_jobs: List[JobResponse] = []
    media_url: Optional[str] = None


class UnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_id: UUID
    source_type: str
    unit_type: str
    content: str
    vision_caption: Optional[str] = None
    ocr_text: Optional[str] = None
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    time_start: Optional[float] = None
    time_end: Optional[float] = None
    image_path: Optional[str] = None
    bounding_box: Optional[dict] = None
    sequence_index: int
    unit_metadata: dict


def _resp(s: Source) -> SourceResponse:
    r = SourceResponse.model_validate(s)
    r.media_url = media_url_for(s.id, s.file_path)
    return r


async def _load(db: AsyncSession, source_id: UUID) -> Source:
    s = (await db.execute(select(Source).options(selectinload(Source.processing_jobs)).where(Source.id == source_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Source not found")
    return s


async def _enqueue_or_fail(db: AsyncSession, source: Source, job: ProcessingJob):
    try:
        await enqueue("ingest_source", str(source.id))
    except Exception as e:  # noqa: BLE001 - never leave a source "queued" forever with no worker
        source.status, source.error_message = "failed", f"Could not enqueue job (is Redis running?): {e}"
        job.state, job.stage, job.error_detail = "failed", "enqueue", {"error": str(e)}
        await db.commit()


@router.post("/courses", response_model=CourseResponse)
async def create_course(p: CourseCreate, db: AsyncSession = Depends(get_db)):
    c = Course(title=p.title, code=p.code, description=p.description)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.get("/courses", response_model=List[CourseResponse])
async def list_courses(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Course).order_by(Course.created_at.desc()))).scalars().all()


@router.post("/sources/upload", response_model=SourceResponse)
async def upload_source(file: UploadFile = File(...), course_id: UUID = Form(...), title: Optional[str] = Form(None),
                        db: AsyncSession = Depends(get_db)):
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()
    if ext not in EXT_TYPES:
        raise HTTPException(400, f"Unsupported file type {ext!r}. Allowed: {', '.join(sorted(EXT_TYPES))}")
    if not await db.get(Course, course_id):
        raise HTTPException(404, "Course not found")
    source_id = uuid.uuid4()
    path = save_uploaded_source(source_id, filename, file.file)
    size = Path(path).stat().st_size
    if size == 0 or size > MAX_BYTES:
        Path(path).unlink(missing_ok=True)
        raise HTTPException(400, "File is empty or larger than 2 GB")
    stype, mime = EXT_TYPES[ext]
    source = Source(id=source_id, course_id=course_id, title=title or filename, source_type=stype, file_path=path,
                    mime_type=mime, file_size_bytes=size, status="queued", source_metadata={"original_filename": filename})
    job = ProcessingJob(source_id=source_id, state="queued", stage="upload_validated", progress_percent=0)
    db.add_all([source, job])
    await db.commit()
    await _enqueue_or_fail(db, source, job)
    return _resp(await _load(db, source_id))


@router.get("/sources", response_model=List[SourceResponse])
async def list_sources(course_id: Optional[UUID] = None, db: AsyncSession = Depends(get_db)):
    q = select(Source).options(selectinload(Source.processing_jobs)).order_by(Source.created_at.desc())
    if course_id:
        q = q.where(Source.course_id == course_id)
    return [_resp(s) for s in (await db.execute(q)).scalars().all()]


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(source_id: UUID, db: AsyncSession = Depends(get_db)):
    return _resp(await _load(db, source_id))


@router.get("/sources/{source_id}/units", response_model=List[UnitResponse])
async def get_units(source_id: UUID, db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(ContentUnit).where(ContentUnit.source_id == source_id)
                             .order_by(ContentUnit.sequence_index))).scalars().all()


@router.get("/units/{unit_id}", response_model=UnitResponse)
async def get_unit(unit_id: UUID, db: AsyncSession = Depends(get_db)):
    u = await db.get(ContentUnit, unit_id)
    if not u:
        raise HTTPException(404, "Unit not found")
    return u


@router.post("/sources/{source_id}/retry", response_model=SourceResponse)
async def retry_source(source_id: UUID, db: AsyncSession = Depends(get_db)):
    s = await _load(db, source_id)
    if s.status not in ("failed", "completed"):
        raise HTTPException(409, f"Source is {s.status}; wait for it to finish")
    attempt = (await db.execute(select(func.coalesce(func.max(ProcessingJob.attempt_number), 0)).where(ProcessingJob.source_id == source_id))).scalar_one() + 1
    job = ProcessingJob(source_id=source_id, state="queued", stage="upload_validated", progress_percent=0, attempt_number=attempt)
    s.status, s.error_message = "queued", None
    db.add(job)
    await db.commit()
    await _enqueue_or_fail(db, s, job)
    return _resp(await _load(db, source_id))


@router.delete("/sources/{source_id}")
async def delete_source(source_id: UUID, db: AsyncSession = Depends(get_db)):
    s = await _load(db, source_id)
    storage = get_storage_path()
    for sub in ("images", "slides", "keyframes"):
        shutil.rmtree(storage / sub / str(source_id), ignore_errors=True)
    Path(s.file_path).unlink(missing_ok=True)
    await db.delete(s)
    await db.commit()
    return {"deleted": str(source_id), "note": "Rebuild the knowledge base to drop its chunks from retrieval."}
