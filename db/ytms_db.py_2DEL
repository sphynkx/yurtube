from typing import Optional, List, Any

async def fetch_video_storage_path(conn, video_id: str, ensure_ready: bool = False) -> Optional[str]:
    if ensure_ready:
        row = await conn.fetchrow(
            "SELECT storage_path FROM videos WHERE video_id = $1 AND processing_status = 'ready'",
            video_id,
        )
    else:
        row = await conn.fetchrow(
            "SELECT storage_path FROM videos WHERE video_id = $1",
            video_id,
        )
    if row and row["storage_path"]:
        return row["storage_path"]
    return None


async def mark_thumbnails_ready(conn, video_id: str) -> None:
    await conn.execute(
        "UPDATE videos SET thumbnails_ready = TRUE WHERE video_id = $1",
        video_id,
    )


async def get_thumbnails_asset_path(conn, video_id: str) -> Optional[str]:
    row = await conn.fetchrow(
        "SELECT path FROM video_assets WHERE video_id = $1 AND asset_type = 'thumbs_vtt'",
        video_id,
    )
    return row["path"] if row else None


async def get_thumbnails_flag(conn, video_id: str) -> bool:
    row = await conn.fetchrow(
        "SELECT thumbnails_ready FROM videos WHERE video_id = $1",
        video_id,
    )
    return bool(row and row["thumbnails_ready"])


async def list_videos_needing_thumbnails(conn, limit: int = 50) -> List[Any]:
    rows = await conn.fetch(
        """
        SELECT video_id, storage_path
        FROM videos
        WHERE processing_status = 'ready'
          AND (thumbnails_ready IS DISTINCT FROM TRUE)
        ORDER BY created_at ASC
        LIMIT $1
        """,
        limit,
    )
    return rows


async def reset_thumbnails_state(conn, video_id: str) -> None:
    await conn.execute(
        "UPDATE videos SET thumbnails_ready = FALSE WHERE video_id = $1",
        video_id,
    )
    await conn.execute(
        "DELETE FROM video_assets WHERE video_id = $1 AND (asset_type = 'thumbs_vtt' OR asset_type LIKE 'sprite:%')",
        video_id,
    )