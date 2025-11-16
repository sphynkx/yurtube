from fastapi import APIRouter, Request, HTTPException
import hmac
import hashlib
import json
import os

from config.ytms_config import YTMS_CALLBACK_SECRET, STORAGE_FS_ROOT, STORAGE_WEB_PREFIX
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset

router = APIRouter(tags=["ytms"])

def _hmac_sha256_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

def _fs_to_web_path(abs_path: str) -> str:
    # Convert absolute fs path under STORAGE_FS_ROOT into web path under STORAGE_WEB_PREFIX
    # Example: /var/www/storage/1v/VID/sprites/thumbs.vtt -> /storage/1v/VID/sprites/thumbs.vtt
    if abs_path.startswith(STORAGE_FS_ROOT.rstrip("/")):
        rel = abs_path[len(STORAGE_FS_ROOT.rstrip("/")):]
        if not rel.startswith("/"):
            rel = "/" + rel
        return STORAGE_WEB_PREFIX.rstrip("/") + rel
    return abs_path  # fallback: return as-is

@router.post("/internal/ytms/thumbnails/callback")
async def ytms_thumbnails_callback(request: Request):
    body = await request.body()
    sig = request.headers.get("X-Signature", "").strip()
    calc = _hmac_sha256_hex(YTMS_CALLBACK_SECRET, body)
    if not sig or not hmac.compare_digest(sig, calc):
        raise HTTPException(status_code=401, detail="invalid_signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    status = payload.get("status")
    video_id = payload.get("video_id")

    if not video_id:
        raise HTTPException(status_code=400, detail="missing_video_id")

    if status != "succeeded":
        # Accept failure callbacks too, but do not write assets
        return {"ok": True, "status": status}

    vtt_info = (payload.get("vtt") or {})
    vtt_rel_path = vtt_info.get("path")  # e.g. "sprites/thumbs.vtt"
    if not vtt_rel_path:
        raise HTTPException(status_code=400, detail="missing_vtt_path")

    # Load absolute storage base path for this video (videos.storage_path)
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT storage_path FROM videos WHERE video_id = $1", video_id)
        if not row or not row["storage_path"]:
            raise HTTPException(status_code=404, detail="storage_path_not_found")
        storage_base: str = row["storage_path"]

        # Build absolute and then web path
        vtt_abs = os.path.normpath(os.path.join(storage_base, vtt_rel_path))
        vtt_web = _fs_to_web_path(vtt_abs)

        # Save in video_assets as 'thumbs_vtt'
        await upsert_video_asset(conn, video_id, "thumbs_vtt", vtt_web)

        return {"ok": True, "status": status, "asset_type": "thumbs_vtt", "path": vtt_web}
    finally:
        await release_conn(conn)