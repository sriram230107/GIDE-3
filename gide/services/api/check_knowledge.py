import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.database.models import ProcessingJob, Source, Chunk, Topic, Concept


async def main():
    async with AsyncSessionLocal() as db:
        jobs = (await db.execute(
            select(ProcessingJob).order_by(ProcessingJob.created_at.desc())
        )).scalars().all()

        print("JOBS:")
        for j in jobs:
            print(
                j.id,
                j.source_id,
                j.state,
                j.stage,
                j.progress_percent,
                j.error_detail
            )

        print("\nKNOWLEDGE:")
        print("chunks:", len((await db.execute(select(Chunk))).scalars().all()))
        print("topics:", len((await db.execute(select(Topic))).scalars().all()))
        print("concepts:", len((await db.execute(select(Concept))).scalars().all()))


asyncio.run(main())