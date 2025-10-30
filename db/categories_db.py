from typing import List

import asyncpg


async def list_categories(conn: asyncpg.Connection) -> List[asyncpg.Record]:
    return await conn.fetch(
        "SELECT category_id, name FROM categories ORDER BY name ASC"
    )


async def category_exists(conn: asyncpg.Connection, category_id: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM categories WHERE category_id = $1",
        category_id,
    )
    return row is not None