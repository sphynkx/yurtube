from typing import List, Optional

import asyncpg


async def create_video(
    conn: asyncpg.Connection,
    video_id: str,
    author_uid: str,
    title: str,
    description: str,
    status: str,
    storage_path: str,
    category_id: Optional[str],
    is_age_restricted: bool,
    is_made_for_kids: bool,
) -> None:
    await conn.execute(
        """
        INSERT INTO videos (
          video_id, author_uid, title, description, duration_sec, status,
          processing_status, storage_path, category_id, is_age_restricted, is_made_for_kids
        )
        VALUES ($1,$2,$3,$4,0,$5,'uploaded',$6,$7,$8,$9)
        """,
        video_id,
        author_uid,
        title,
        description,
        status,
        storage_path,
        category_id,
        is_age_restricted,
        is_made_for_kids,
    )


async def set_video_ready(
    conn: asyncpg.Connection, video_id: str, duration_sec: Optional[int]
) -> None:
    if duration_sec is None:
        await conn.execute(
            """
            UPDATE videos
            SET processing_status = 'ready'
            WHERE video_id = $1
            """,
            video_id,
        )
    else:
        await conn.execute(
            """
            UPDATE videos
            SET processing_status = 'ready', duration_sec = $2
            WHERE video_id = $1
            """,
            video_id,
            duration_sec,
        )


async def list_latest_public_videos(conn: asyncpg.Connection, limit: int = 20) -> List[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT v.*, u.username, a.path AS thumb_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        WHERE v.status = 'public' AND v.processing_status = 'ready'
        ORDER BY v.created_at DESC
        LIMIT $1
        """,
        limit,
    )


async def get_video(conn: asyncpg.Connection, video_id: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        """
        SELECT v.*, u.username
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        WHERE v.video_id = $1
        """,
        video_id,
    )


async def list_my_videos(conn: asyncpg.Connection, author_uid: str, limit: int = 100) -> List[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT v.*, a.path AS thumb_asset_path
        FROM videos v
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        WHERE v.author_uid = $1
        ORDER BY v.created_at DESC
        LIMIT $2
        """,
        author_uid,
        limit,
    )