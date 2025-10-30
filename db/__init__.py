import asyncio
import logging
from typing import Optional

import asyncpg

from config.config import settings

_pool: Optional[asyncpg.Pool] = None

logger = logging.getLogger(__name__)


async def init_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=10)
        logger.info("PostgreSQL pool initialized")
    return _pool


async def get_conn() -> asyncpg.Connection:
    if _pool is None:
        await init_db_pool()
    assert _pool is not None
    return await _pool.acquire()


async def release_conn(conn: asyncpg.Connection) -> None:
    if _pool is not None:
        await _pool.release(conn)


async def shutdown_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")