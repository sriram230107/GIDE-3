import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from app.core.database import AsyncSessionLocal, init_db
from app.database.models import Course, Source, ContentUnit

@pytest.mark.asyncio
async def test_db_check_constraint_rejects_missing_location():
    """
    Condition 8 Test:
    Proves that the PostgreSQL engine CHECK constraint actively rejects any ContentUnit
    that lacks valid location coordinates for its source type.
    """
    await init_db()

    async with AsyncSessionLocal() as session:
        # Create prerequisite Course & Source
        course = Course(title="Constraint Test Course")
        session.add(course)
        await session.commit()
        await session.refresh(course)

        source = Source(
            course_id=course.id,
            title="Constraint Test Source",
            source_type="pdf",
            file_path="dummy.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            status="queued"
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        
        # Save ID to avoid lazy loading after rollbacks
        source_id = source.id

        # 1. Invalid PDF unit: missing page_number
        invalid_pdf_unit = ContentUnit(
            source_id=source_id,
            source_type="pdf",
            unit_type="text",
            content="Missing page number in PDF unit",
            page_number=None,  # VIOLATES CHECK CONSTRAINT!
            sequence_index=0
        )
        session.add(invalid_pdf_unit)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        
        assert "ck_content_unit_provenance_by_source_type" in str(exc_info.value).lower()
        await session.rollback()

        # 2. Invalid PPTX unit: missing slide_number
        invalid_pptx_unit = ContentUnit(
            source_id=source_id,
            source_type="pptx",
            unit_type="slide",
            content="Missing slide number in PPTX unit",
            slide_number=None,  # VIOLATES CHECK CONSTRAINT!
            sequence_index=1
        )
        session.add(invalid_pptx_unit)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        
        assert "ck_content_unit_provenance_by_source_type" in str(exc_info.value).lower()
        await session.rollback()

        # 3. Invalid Video unit: missing time_start / time_end
        invalid_video_unit = ContentUnit(
            source_id=source_id,
            source_type="video",
            unit_type="caption",
            content="Missing timestamps in video caption",
            time_start=None,  # VIOLATES CHECK CONSTRAINT!
            time_end=None,
            sequence_index=2
        )
        session.add(invalid_video_unit)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        
        assert "ck_content_unit_provenance_by_source_type" in str(exc_info.value).lower()
        await session.rollback()

        # 4. Valid PDF unit: has page_number=1 -> MUST SUCCEED
        valid_unit = ContentUnit(
            source_id=source_id,
            source_type="pdf",
            unit_type="text",
            content="Properly located unit on page 1",
            page_number=1,
            sequence_index=3
        )
        session.add(valid_unit)
        await session.commit()
        await session.refresh(valid_unit)
        assert valid_unit.id is not None
        assert valid_unit.page_number == 1
