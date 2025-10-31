from typing import Optional

import asyncpg


async def get_user_avatar_path(conn: asyncpg.Connection, user_uid: str) -> Optional[str]:
    row = await conn.fetchrow(
        """
        SELECT path
        FROM user_assets
        WHERE user_uid = $1 AND asset_type = 'avatar'
        """,
        user_uid,
    )
    return row["path"] if row else None


async def upsert_user_avatar(conn: asyncpg.Connection, user_uid: str, rel_path: str) -> None:
    await conn.execute(
        """
        INSERT INTO user_assets (user_uid, asset_type, path)
        VALUES ($1, 'avatar', $2)
        ON CONFLICT (user_uid, asset_type)
        DO UPDATE SET path = EXCLUDED.path
        """,
        user_uid,
        rel_path,
    )


async def delete_user_avatar(conn: asyncpg.Connection, user_uid: str) -> None:
    await conn.execute(
        """
        DELETE FROM user_assets
        WHERE user_uid = $1 AND asset_type = 'avatar'
        """,
        user_uid,
    )