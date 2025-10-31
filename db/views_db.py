from typing import Optional

import asyncpg

from utils.idgen_ut import gen_id


async def add_view(
    conn: asyncpg.Connection,
    video_id: str,
    user_uid: Optional[str],
    duration_sec: int = 0,
) -> None:
    view_uid = gen_id(20)
    await conn.execute(
        """
        INSERT INTO views (view_uid, user_uid, video_id, duration_sec)
        VALUES ($1, $2, $3, $4)
        """,
        view_uid,
        user_uid,
        video_id,
        duration_sec,
    )


async def increment_video_views_counter(
    conn: asyncpg.Connection,
    video_id: str,
) -> None:
    await conn.execute(
        """
        UPDATE videos SET views_count = views_count + 1
        WHERE video_id = $1
        """,
        video_id,
    )


async def clear_history(
    conn: asyncpg.Connection,
    user_uid: str,
) -> None:
    await conn.execute(
        """
        DELETE FROM views
        WHERE user_uid = $1
        """,
        user_uid,
    )


async def remove_history_for_video(
    conn: asyncpg.Connection,
    user_uid: str,
    video_id: str,
) -> None:
    await conn.execute(
        """
        DELETE FROM views
        WHERE user_uid = $1 AND video_id = $2
        """,
        user_uid,
        video_id,
    )