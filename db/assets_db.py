import re
from typing import List, Optional
import asyncpg


async def upsert_video_asset(
    conn: asyncpg.Connection,
    video_id: str,
    asset_type: str,
    path: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO video_assets (asset_id, video_id, asset_type, path)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (video_id, asset_type)
        DO UPDATE SET path = EXCLUDED.path, created_at = NOW()
        """,
        f"{video_id}:{asset_type}",
        video_id,
        asset_type,
        path,
    )


async def get_thumbnail_asset_path(conn: asyncpg.Connection, video_id: str) -> Optional[str]:
    row = await conn.fetchrow(
        """
        SELECT path
        FROM video_assets
        WHERE video_id = $1 AND asset_type = 'thumbnail_default'
        """,
        video_id,
    )
    return row["path"] if row else None


async def get_thumbnail_anim_asset_path(conn: asyncpg.Connection, video_id: str) -> Optional[str]:
    row = await conn.fetchrow(
        """
        SELECT path
        FROM video_assets
        WHERE video_id = $1 AND asset_type = 'thumbnail_anim'
        """,
        video_id,
    )
    return row["path"] if row else None



async def get_video_sprite_assets(conn, video_id: str) -> List[str]:
    rows = await conn.fetch(
        "SELECT asset_type, path FROM video_assets WHERE video_id = $1 AND asset_type LIKE 'sprite:%' ORDER BY asset_type ASC",
        video_id,
    )
    return [r["path"] for r in rows if r.get("path")]


async def get_thumbs_vtt_asset(conn, video_id: str) -> Optional[str]:
    row = await conn.fetchrow(
        "SELECT path FROM video_assets WHERE video_id = $1 AND asset_type = 'thumbs_vtt'",
        video_id,
    )
    return row["path"] if row else None

