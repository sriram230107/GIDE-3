import asyncio
from app.core.database import async_engine, Base
from app.database import models  # to load models
async def drop_all():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("Dropped all tables")
        await conn.run_sync(Base.metadata.create_all)
        print("Created all tables")

if __name__ == "__main__":
    asyncio.run(drop_all())
