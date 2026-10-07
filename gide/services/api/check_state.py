import asyncio
from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.database.models import Source, ContentUnit, Chunk, Topic, Concept


async def main():
    async with AsyncSessionLocal() as db:
        sources = (await db.execute(select(Source))).scalars().all()
        units = await db.scalar(select(func.count()).select_from(ContentUnit))
        chunks = await db.scalar(select(func.count()).select_from(Chunk))
        topics = await db.scalar(select(func.count()).select_from(Topic))
        concepts = await db.scalar(select(func.count()).select_from(Concept))

        print("SOURCES:")
        for s in sources:
            print(s.id, s.title, s.status, s.error_message)

        print("\nCOUNTS:")
        print("content_units:", units)
        print("chunks:", chunks)
        print("topics:", topics)
        print("concepts:", concepts)


asyncio.run(main())