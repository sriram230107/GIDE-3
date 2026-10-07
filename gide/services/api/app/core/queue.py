from arq import create_pool
from arq.connections import RedisSettings
from app.core.config import settings


def redis_settings() -> RedisSettings:
    return RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)


async def enqueue(job_name: str, *args):
    """Enqueue an Arq job. Raises if Redis is unreachable (callers must surface that, never hide it)."""
    pool = await create_pool(redis_settings())
    try:
        return await pool.enqueue_job(job_name, *args)
    finally:
        await pool.close()
