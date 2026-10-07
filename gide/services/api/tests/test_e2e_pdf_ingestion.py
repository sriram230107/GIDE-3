from pathlib import Path as _P
FIXTURE = _P(__file__).parent / 'fixtures' / 'sample_textbook.pdf'
import shutil
import uuid
import pytest
from pathlib import Path
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, init_db
from app.core.storage import get_storage_path
from app.database.models import Course, Source, ProcessingJob, ContentUnit
from app.worker import ingest_source as process_pdf_source

@pytest.mark.asyncio
async def test_e2e_pdf_ingestion_real_fixture():
    await init_db()
    fixture_src = Path(str(FIXTURE))
    assert fixture_src.exists()

    async with AsyncSessionLocal() as session:
        # Create course
        course = Course(title="E2E Test Course", code="E2E100")
        session.add(course)
        await session.commit()
        await session.refresh(course)

        # Copy fixture into storage
        source_id = uuid.uuid4()
        storage = get_storage_path()
        dest_pdf = storage / "sources" / f"{source_id}.pdf"
        shutil.copyfile(fixture_src, dest_pdf)

        source = Source(
            id=source_id,
            course_id=course.id,
            title="Introduction to Machine Learning Textbook",
            source_type="pdf",
            file_path=str(dest_pdf),
            mime_type="application/pdf",
            file_size_bytes=dest_pdf.stat().st_size,
            status="queued"
        )
        session.add(source)

        job = ProcessingJob(
            source_id=source_id,
            state="queued",
            stage="upload_validated",
            progress_percent=0
        )
        session.add(job)
        await session.commit()

    # Execute the real ingestion worker task
    await process_pdf_source(None, str(source_id))

    # Verify database state after processing
    async with AsyncSessionLocal() as session:
        res_source = await session.execute(select(Source).where(Source.id == source_id))
        saved_source = res_source.scalar_one()

        assert saved_source.status == "completed", f"Expected completed, got {saved_source.status}, err: {saved_source.error_message}"
        assert saved_source.source_metadata["page_count"] == 3
        assert saved_source.source_metadata["unit_count"] >= 4

        res_job = await session.execute(select(ProcessingJob).where(ProcessingJob.source_id == source_id))
        saved_job = res_job.scalar_one()
        assert saved_job.state == "completed"
        assert saved_job.progress_percent == 100

        # Query extracted ContentUnit rows
        res_units = await session.execute(
            select(ContentUnit)
            .where(ContentUnit.source_id == source_id)
            .order_by(ContentUnit.sequence_index.asc())
        )
        units = res_units.scalars().all()
        assert len(units) >= 4

        # Verify page provenance
        pages_found = {u.page_number for u in units}
        assert pages_found == {1, 2, 3}

        for u in units:
            assert u.source_id == source_id
            assert u.page_number is not None
            assert u.page_number > 0
            assert len(u.content) > 0
