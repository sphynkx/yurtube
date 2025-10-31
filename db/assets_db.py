from typing import Optional

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