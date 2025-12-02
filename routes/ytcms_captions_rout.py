import os
import json
import asyncio
from typing import Optional, Any

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import get_owned_video, set_video_ready
from db.ytms_db import fetch_video_storage_path
from db.captions_db import set_video_captions, reset_video_captions, get_video_captions_status
from utils.security_ut import get_current_user
from services.ytcms.captions_generation import generate_captions
from services.ffmpeg_srv import async_probe_duration_seconds

router = APIRouter(tags=["captions"])

AUTO_MIN_DURATION = getattr(settings, "AUTO_CAPTIONS_MIN_DURATION", 3)


@router.post("/manage/video/{video_id}/captions/process")
async def captions_process(
    request: Request,
    video_id: str,
    lang: str = Form("auto"),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        duration = int(owned.get("duration_sec") or 0)
        storage_rel = owned["storage_path"].rstrip("/")
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", "/var/www/storage")
    original_abs = os.path.join(abs_root, storage_rel, "original.webm")
    if not os.path.exists(original_abs):
        try:
            dsec = await async_probe_duration_seconds(original_abs)
            if dsec and dsec > 0:
                duration = int(dsec)
        except Exception:
            pass
        if not os.path.exists(original_abs):
            return JSONResponse({"ok": False, "error": "original_missing"}, status_code=404)

    async def _bg_worker():
        try:
            rel_vtt, meta = await generate_captions(
                video_id=video_id,
                storage_rel=storage_rel,
                src_path=original_abs,
                lang=lang,
            )
            c = await get_conn()
            try:
                await set_video_captions(c, video_id, rel_vtt, meta.get("lang") or lang, meta)
            finally:
                await release_conn(c)
            print(f"[YTCMS] captions done video_id={video_id} lang={meta.get('lang')} vtt={rel_vtt}")
        except Exception as e:
            print(f"[YTCMS] captions failed video_id={video_id}: {e}")

    asyncio.create_task(_bg_worker())
    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


@router.get("/internal/ytcms/captions/status")
async def captions_status(video_id: str = Query(...)):
    """
    Return normalized status so UI can render correctly:
    - status: one of idle | queued | processing | done | error | not_found
    - has_vtt: True/False
    - rel_vtt: relative path to vtt (if any)
    - lang, job_id: optional meta hints
    """
    conn = await get_conn()
    try:
        row = await get_video_captions_status(conn, video_id)
        print(f"STATUSES from YTCMS: {row}")
    finally:
        await release_conn(conn)

    # No record -> idle (no job and no file)
    if not row:
        return {
            "ok": True,
            "video_id": video_id,
            "status": "idle",
            "has_vtt": False,
            "rel_vtt": None,
            "lang": None,
            "job_id": None,
        }

    # Map various schemas to normalized fields
    ready = bool(row.get("captions_ready") or row.get("ready"))
    rel_vtt = row.get("captions_vtt") or row.get("rel_vtt")
    lang = row.get("captions_lang") or row.get("lang")
    meta = row.get("captions_meta") or row.get("meta") or {}
    job_id = None
    try:
        if isinstance(meta, dict):
            job_id = meta.get("job_id")
    except Exception:
        job_id = None

    # Determine status:
    # If we have a vtt saved -> done
    # Else if job_id exists -> queued/processing, but we cannot know which one without service poll here.
    # For UI simplicity treat presence of job_id as queued (will be updated by separate JS polling against service, if needed).
    if ready or rel_vtt:
        norm_status = "done"
    elif job_id:
        # Assume queued until worker flips DB to ready
        norm_status = "queued"
    else:
        norm_status = "idle"

    return {
        "ok": True,
        "video_id": video_id,
        "status": norm_status,
        "has_vtt": bool(rel_vtt),
        "rel_vtt": rel_vtt,
        "lang": lang,
        "job_id": job_id,
    }


@router.post("/internal/ytcms/captions/retry")
async def captions_retry(
    request: Request,
    video_id: str = Form(...),
    lang: str = Form("auto"),
    csrf_token: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login_required")

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="not_found")
        storage_rel = (owned.get("storage_path") or "").strip().rstrip("/")
        if not storage_rel:
            raise HTTPException(status_code=404, detail="storage_missing")
        await reset_video_captions(conn, video_id)
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", "/var/www/storage")
    original_abs = os.path.join(abs_root, storage_rel, "original.webm")
    if not os.path.exists(original_abs):
        print(f"[YTCMS] retry original missing video_id={video_id} path={original_abs}")
        raise HTTPException(status_code=404, detail="original_missing")

    async def _bg_worker():
        try:
            rel_vtt, meta = await generate_captions(
                video_id=video_id,
                storage_rel=storage_rel,
                src_path=original_abs,
                lang=lang,
            )
            c = await get_conn()
            try:
                await set_video_captions(c, video_id, rel_vtt, meta.get("lang") or lang, meta)
            finally:
                await release_conn(c)
            print(f"[YTCMS] captions retry done video_id={video_id} lang={meta.get('lang')} vtt={rel_vtt}")
        except Exception as e:
            print(f"[YTCMS] captions retry failed video_id={video_id}: {e}")

    asyncio.create_task(_bg_worker())
    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


@router.post("/internal/ytcms/captions/delete")
async def captions_delete(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login_required")

    conn = await get_conn()
    try:
        storage_rel = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
        if not storage_rel:
            raise HTTPException(status_code=404, detail="video_not_ready")
        await reset_video_captions(conn, video_id)
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", "/var/www/storage")
    captions_dir = os.path.join(abs_root, storage_rel, "captions")
    try:
        if os.path.isdir(captions_dir):
            for root, dirs, files in os.walk(captions_dir, topdown=False):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except Exception:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception:
                        pass
            try:
                os.rmdir(captions_dir)
            except Exception:
                pass
    except Exception as e:
        print(f"[YTCMS] captions delete fs error video_id={video_id}: {e}")

    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)