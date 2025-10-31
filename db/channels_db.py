from typing import Optional

import asyncpg


async def get_user_by_username(conn: asyncpg.Connection, username: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        """
        SELECT user_uid, username, channel_id, created_at
        FROM users
        WHERE username = $1
        """,
        username,
    )


async def get_user_by_channel_id(conn: asyncpg.Connection, channel_id: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        """
        SELECT user_uid, username, channel_id, created_at
        FROM users
        WHERE channel_id = $1
        """,
        channel_id,
    )