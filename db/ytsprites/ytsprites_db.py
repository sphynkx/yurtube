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

async def persist_vtt_asset(conn, video_id: str, web_path: str) -> None:
    """
    Record (or replace) VTT for video.
    asset_type: 'thumbs_vtt'
    path: web path (e.g. '/storage/.../sprites.vtt')
    """
    # Delete possible previous
    await conn.execute(
        "DELETE FROM video_assets WHERE video_id = $1 AND asset_type = 'thumbs_vtt'",
        video_id,
    )
    await conn.execute(
        "INSERT INTO video_assets (video_id, asset_type, path) VALUES ($1, 'thumbs_vtt', $2)",
        video_id,
        web_path,
    )

async def persist_sprite_assets(conn, video_id: str, web_paths: List[str]) -> None:
    """
    Record sprites for video.
    asset_type: 'sprite:<filename>'
    path: web path (e.g. '/storage/.../sprite_0001.jpg')
    """
    # Delete possible previous
    await conn.execute(
        "DELETE FROM video_assets WHERE video_id = $1 AND asset_type LIKE 'sprite:%'",
        video_id,
    )
    for wp in web_paths:
        name = (wp.rsplit("/", 1)[-1] if wp else "").strip()
        if not name:
            continue
        asset_type = f"sprite:{name}"
        await conn.execute(
            "INSERT INTO video_assets (video_id, asset_type, path) VALUES ($1, $2, $3)",
            video_id,
            asset_type,
            wp,
        )