from __future__ import annotations

from typing import Optional


async def upsert_video_rendition(
    conn,
    *,
    video_id: str,
    preset: str,
    codec: str,
    status: str,
    storage_path: Optional[str],
    error_message: Optional[str] = None,
) -> None:
    """
    Upsert into video_renditions by (video_id, preset, codec).
    status: queued|processing|ready|error
    """
    q = """
    INSERT INTO video_renditions (video_id, preset, codec, status, storage_path, error_message, created_at, updated_at)
    VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
    ON CONFLICT (video_id, preset, codec) DO UPDATE
      SET status = EXCLUDED.status,
          storage_path = EXCLUDED.storage_path,
          error_message = EXCLUDED.error_message,
          updated_at = NOW()
    """
    await conn.execute(q, video_id, preset, codec, status, storage_path, error_message)