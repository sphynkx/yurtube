from __future__ import annotations
from typing import Optional, Any, Dict
import re


async def delete_video_asset_by_type(conn, *, video_id: str, asset_type: str) -> Optional[str]:
    """
    Delete video asset row by (video_id, asset_type) and return its path.
    """
    asset_type = (asset_type or "").strip()
    asset_type = re.sub(r"[^a-zA-Z0-9._-]+", "_", asset_type)[:64]

    row = await conn.fetchrow(
        """
        DELETE FROM video_assets
        WHERE video_id = $1 AND asset_type = $2
        RETURNING path
        """,
        video_id,
        asset_type,
    )
    return (row["path"] if row and "path" in row else None)


async def upsert_video_asset_path(conn, *, video_id: str, asset_type: str, path: str) -> None:
    """
    Upsert record in video_assets for given (video_id, asset_type).
    Uses deterministic asset_id (TEXT PK) to avoid needing id generator.
    """
    asset_type = (asset_type or "").strip() or "asset"
    asset_type = re.sub(r"[^a-zA-Z0-9._-]+", "_", asset_type)[:64]

    q = """
    INSERT INTO video_assets (asset_id, video_id, asset_type, path, created_at)
    VALUES ($1, $2, $3, $4, NOW())
    ON CONFLICT (video_id, asset_type) DO UPDATE
      SET path = EXCLUDED.path
    """
    asset_id = f"{video_id}:{asset_type}"
    await conn.execute(q, asset_id, video_id, asset_type, path)