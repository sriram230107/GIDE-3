import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.database.models import Source, ContentUnit
from app.knowledge.chunking import chunk_units, search_text

async def main():
    async with AsyncSessionLocal() as s:
        sources = (await s.execute(
            select(Source).where(Source.status == "completed")
        )).scalars().all()

        for source in sources:
            units = (await s.execute(
                select(ContentUnit)
                .where(ContentUnit.source_id == source.id)
                .order_by(ContentUnit.sequence_index)
            )).scalars().all()

            data = []

            for u in units:
                data.append({
                    "id": str(u.id),
                    "source_type": u.source_type,
                    "unit_type": u.unit_type,
                    "sequence_index": u.sequence_index,
                    "page_number": u.page_number,
                    "slide_number": u.slide_number,
                    "time_start": u.time_start,
                    "time_end": u.time_end,
                    "text": search_text(u.content, u.vision_caption, u.ocr_text),
                })

            chunks = chunk_units(data)

            print(f"Source: {source.filename}")
            print(f"ContentUnits: {len(units)}")
            print(f"Chunks produced: {len(chunks)}")
            print()

            for i, c in enumerate(chunks):
                print(f"CHUNK {i + 1}")
                print(f"  Units: {len(c['unit_ids'])}")
                print(f"  Location: {c['location']}")
                print(f"  Text: {c['text'][:180].replace(chr(10), ' ')}")
                print()

asyncio.run(main())
