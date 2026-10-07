import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from app.core.config import settings
from app.database.models import Base

async_engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True, poolclass=NullPool)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)
sync_engine = create_engine(settings.SYNC_DATABASE_URL, echo=False, future=True)


async def init_db():
    """Create tables that do not exist yet. NOTE: create_all never alters existing tables;
    if you change a model, drop the dev DB or add a migration."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
