from __future__ import annotations

import re


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