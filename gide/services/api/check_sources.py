import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.database.models import Source

async def main():
    async with AsyncSessionLocal() as s:
        sources = (await s.execute(select(Source))).scalars().all()

        print(f"Sources found: {len(sources)}")

        for src in sources:
            print(f"ID:     {src.id}")
            print(f"Status: {src.status}")
            print(f"Type:   {src.source_type}")
            print(f"File:   {getattr(src, 'filename', 'N/A')}")
            print()

asyncio.run(main())
