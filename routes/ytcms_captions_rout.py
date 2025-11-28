import os
import json
import asyncio
from typing import Optional, Any

from fastapi import APIRouter, Request, Form, HTTPException
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
        return JSONResponse({"ok": False, "error": "original_missing"}, status_code=404)

    # If duration is zero in DB, try to re-probe and persist
    if duration <= 0:
        try:
            duration = await async_probe_duration_seconds(original_abs)
            conn = await get_conn()
            try:
                await set_video_ready(conn, video_id, duration)
            finally:
                await release_conn(conn)
        except Exception:
            return JSONResponse({"ok": False, "error": "too_short", "duration": 0}, status_code=400)

    if duration < AUTO_MIN_DURATION:
        return JSONResponse({"ok": False, "error": "too_short", "duration": duration}, status_code=400)

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

    # Fire-and-forget background job to avoid 504
    asyncio.create_task(_bg_worker())

    # Redirect back to media page
    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


@router.get("/internal/ytcms/captions/status")
async def captions_status(video_id: str):
    conn = await get_conn()
    try:
        status = await get_video_captions_status(conn, video_id)
    finally:
        await release_conn(conn)
    if not status:
        return {"ok": False, "error": "not_found"}
    return {
        "ok": True,
        "video_id": video_id,
        "ready": status["captions_ready"],
        "lang": status["captions_lang"],
        "vtt": status["captions_vtt"],
        "meta": status["captions_meta"],
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
        storage_rel = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
        if not storage_rel:
            raise HTTPException(status_code=404, detail="video_not_ready")
        await reset_video_captions(conn, video_id)
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", "/var/www/storage")
    original_abs = os.path.join(abs_root, storage_rel, "original.webm")
    if not os.path.exists(original_abs):
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