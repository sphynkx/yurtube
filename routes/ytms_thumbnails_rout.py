import hmac
import hashlib
import json
import os
from fastapi import APIRouter, Request, HTTPException
from config.ytms_config import (
    YTMS_CALLBACK_SECRET,
    STORAGE_FS_ROOT,
    STORAGE_WEB_PREFIX,
    YTMS_BASE_URL,
)
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset
from services.ytms_client import create_thumbnails_job

router = APIRouter(tags=["ytms"])

def _hmac_sha256_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

def _fs_to_web_path(abs_path: str) -> str:
    if abs_path.startswith(STORAGE_FS_ROOT.rstrip("/")):
        rel = abs_path[len(STORAGE_FS_ROOT.rstrip("/")):]
        if not rel.startswith("/"):
            rel = "/" + rel
        return STORAGE_WEB_PREFIX.rstrip("/") + rel
    return abs_path

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
        return {"ok": True, "status": status}

    vtt_info = (payload.get("vtt") or {})
    vtt_rel_path = vtt_info.get("path")
    if not vtt_rel_path:
        raise HTTPException(status_code=400, detail="missing_vtt_path")

    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT storage_path FROM videos WHERE video_id = $1", video_id)
        if not row or not row["storage_path"]:
            raise HTTPException(status_code=404, detail="storage_path_not_found")
        storage_base: str = row["storage_path"]
        vtt_abs = os.path.normpath(os.path.join(storage_base, vtt_rel_path))
        vtt_web = _fs_to_web_path(vtt_abs)

        await upsert_video_asset(conn, video_id, "thumbs_vtt", vtt_web)

        try:
            await conn.execute("UPDATE videos SET thumbnails_ready = TRUE WHERE video_id = $1", video_id)
        except Exception:
            pass

        return {"ok": True, "status": status, "asset_type": "thumbs_vtt", "path": vtt_web}
    finally:
        await release_conn(conn)

@router.post("/internal/ytms/thumbnails/retry")
async def ytms_thumbnails_retry(video_id: str):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT storage_path FROM videos WHERE video_id = $1 AND processing_status = 'ready'",
            video_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="video_not_ready")
        storage_base: str = row["storage_path"]
    finally:
        await release_conn(conn)

    original_path = os.path.join(storage_base, "original.mp4")
    if not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="original_missing")

    job = await create_thumbnails_job(
        video_id=video_id,
        src_path=original_path,
        out_base_path=storage_base,
        extra=None,
    )
    return {"ok": True, "job": job}

@router.get("/internal/ytms/thumbnails/status")
async def ytms_thumbnails_status(video_id: str):
    conn = await get_conn()
    try:
        asset_row = await conn.fetchrow(
            "SELECT path FROM video_assets WHERE video_id = $1 AND asset_type = 'thumbs_vtt'",
            video_id,
        )
        flag_row = await conn.fetchrow(
            "SELECT thumbnails_ready FROM videos WHERE video_id = $1",
            video_id,
        )
        return {
            "ok": True,
            "video_id": video_id,
            "ready": bool(flag_row and flag_row["thumbnails_ready"]),
            "vtt_path": asset_row["path"] if asset_row else None,
        }
    finally:
        await release_conn(conn)

@router.post("/internal/ytms/thumbnails/backfill")
async def ytms_thumbnails_backfill(limit: int = 50):
    conn = await get_conn()
    to_schedule = []
    try:
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
        for r in rows:
            vid = r["video_id"]
            base = r["storage_path"]
            original_path = os.path.join(base, "original.mp4")
            if not os.path.exists(original_path):
                continue
            to_schedule.append((vid, base, original_path))
    finally:
        await release_conn(conn)

    jobs = []
    for vid, base, orig in to_schedule:
        job = await create_thumbnails_job(
            video_id=vid,
            src_path=orig,
            out_base_path=base,
        )
        jobs.append({"video_id": vid, "job_id": job.get("job_id")})

    return {"ok": True, "scheduled": jobs}