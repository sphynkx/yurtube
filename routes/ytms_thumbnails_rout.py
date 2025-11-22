import hmac
import hashlib
import json
import os
from typing import Any, Optional, Dict, List

import httpx
import aiofiles
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.ytms_config import (
    YTMS_CALLBACK_SECRET,
    STORAGE_FS_ROOT,
    STORAGE_WEB_PREFIX,
    YTMS_BASE_URL,
)
from config.config import settings
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset
from db.ytms_db import (
    fetch_video_storage_path,
    mark_thumbnails_ready,
    get_thumbnails_asset_path,
    get_thumbnails_flag,
    list_videos_needing_thumbnails,
)
from db.videos_db import get_owned_video
from services.ytms_client_srv import create_thumbnails_job
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

router = APIRouter(tags=["ytms"])
templates = Jinja2Templates(directory="templates")

def _csrf_cookie_name() -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")

def _get_csrf_cookie(request: Request) -> str:
    return (request.cookies.get(_csrf_cookie_name()) or "").strip()

def _gen_csrf_token() -> str:
    import secrets
    return secrets.token_urlsafe(32)

def _ensure_csrf_cookie(request: Request, response) -> None:
    if not _get_csrf_cookie(request):
        tok = _gen_csrf_token()
        response.set_cookie(
            _csrf_cookie_name(), tok,
            httponly=False, secure=True, samesite="lax", path="/"
        )

def _validate_csrf(request: Request, form_token: Optional[str]) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    form_tok = (form_token or "").strip()
    if not cookie_tok or not form_tok:
        return False
    try:
        import secrets as _sec
        return _sec.compare_digest(cookie_tok, form_tok)
    except Exception:
        return False

def _hmac_sha256_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

def _fs_to_web_path(abs_path: str) -> str:
    root_norm = STORAGE_FS_ROOT.rstrip("/")
    if abs_path.startswith(root_norm):
        rel = abs_path[len(root_norm):]
        if not rel.startswith("/"):
            rel = "/" + rel
        return STORAGE_WEB_PREFIX.rstrip("/") + rel
    return abs_path

@router.get("/manage/video/{video_id}/media", response_class=HTMLResponse)
async def video_media_page(request: Request, video_id: str) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")
        thumb_rel = owned.get("thumb_asset_path")
        thumb_url = build_storage_url(thumb_rel) if thumb_rel else None
        assets = {
            "thumb_asset_path": thumb_rel,
            "thumb_url": thumb_url,
            "captions_vtt": owned.get("captions_vtt"),
            "thumbs_vtt": owned.get("thumbs_vtt"),
        }
    finally:
        await release_conn(conn)

    csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()
    resp = templates.TemplateResponse(
        "manage/video_media.html",
        {
            "request": request,
            "current_user": user,
            "video_id": video_id,
            "assets": assets,
            "csrf_token": csrf_token,
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        },
    )
    if not _get_csrf_cookie(request):
        resp.set_cookie(_csrf_cookie_name(), csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return resp


@router.post("/manage/video/{video_id}/media/process")
async def start_media_process(
    request: Request,
    video_id: str,
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)
    if not _validate_csrf(request, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

        storage_rel = owned["storage_path"].rstrip("/")
        abs_root = getattr(settings, "STORAGE_ROOT", STORAGE_FS_ROOT)
        out_base_path = os.path.join(abs_root, storage_rel)
        src_path = os.path.join(out_base_path, "original.webm")
        if not os.path.exists(src_path):
            return JSONResponse({"ok": False, "error": "original_missing"}, status_code=404)

        job = await create_thumbnails_job(
            video_id=video_id,
            src_path=src_path,
            out_base_path=out_base_path,
            src_url=None,
            extra=None,
        )
    finally:
        await release_conn(conn)

    # 2DEL - debug ytms
    print("[YTMS PROCESS RESPONSE]", job)

    # Normalize response - if ok isnt present but present  job_id/job/id assume as success
    if "ok" not in job:
        if any(k in job for k in ("job_id", "job", "id")):
            job["ok"] = True
        else:
            job = {"ok": False, "error": "empty_job_response", "raw": job}

    return JSONResponse(job)


@router.get("/manage/ytms/status/{job_id}")
async def media_job_status(job_id: str) -> Any:
    # todo
    base_url = YTMS_BASE_URL.rstrip("/")
    if not base_url:
        return JSONResponse({"ok": False, "error": "ytms_not_configured"}, status_code=500)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(f"{base_url}/jobs/{job_id}")
            r.raise_for_status()
            return JSONResponse(r.json())
        except httpx.HTTPStatusError as e:
            return JSONResponse({"ok": False, "error": "ytms_status_failed", "status": e.response.status_code}, status_code=502)
        except Exception as e:
            return JSONResponse({"ok": False, "error": "ytms_unreachable", "detail": str(e)}, status_code=502)

@router.post("/manage/ytms/fetch_result")
async def media_fetch_result(
    request: Request,
    job_id: str = Form(...),
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    # todo
    return JSONResponse({"ok": False, "error": "not_implemented"}, status_code=501)

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
        storage_base = await fetch_video_storage_path(conn, video_id)
        if not storage_base:
            raise HTTPException(status_code=404, detail="storage_path_not_found")

        abs_root = getattr(settings, "STORAGE_ROOT", STORAGE_FS_ROOT)
        vtt_abs = os.path.normpath(os.path.join(abs_root, storage_base, vtt_rel_path))
        vtt_web = _fs_to_web_path(vtt_abs)
        await upsert_video_asset(conn, video_id, "thumbs_vtt", vtt_web)

        try:
            await mark_thumbnails_ready(conn, video_id)
        except Exception:
            pass

        return {"ok": True, "status": status, "asset_type": "thumbs_vtt", "path": vtt_web}
    finally:
        await release_conn(conn)

@router.post("/internal/ytms/thumbnails/retry")
async def ytms_thumbnails_retry(video_id: str):
    conn = await get_conn()
    try:
        storage_base = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
        if not storage_base:
            raise HTTPException(status_code=404, detail="video_not_ready")
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", STORAGE_FS_ROOT)
    original_path = os.path.join(abs_root, storage_base, "original.webm")
    if not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="original_missing")

    job = await create_thumbnails_job(
        video_id=video_id,
        src_path=original_path,
        out_base_path=os.path.join(abs_root, storage_base),
        extra=None,
    )
    return {"ok": True, "job": job}

@router.get("/internal/ytms/thumbnails/status")
async def ytms_thumbnails_status(video_id: str):
    conn = await get_conn()
    try:
        asset_path = await get_thumbnails_asset_path(conn, video_id)
        ready_flag = await get_thumbnails_flag(conn, video_id)
        return {
            "ok": True,
            "video_id": video_id,
            "ready": bool(ready_flag),
            "vtt_path": asset_path,
        }
    finally:
        await release_conn(conn)

@router.post("/internal/ytms/thumbnails/backfill")
async def ytms_thumbnails_backfill(limit: int = 50):
    conn = await get_conn()
    try:
        rows = await list_videos_needing_thumbnails(conn, limit=limit)
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", STORAGE_FS_ROOT)
    jobs = []
    for r in rows:
        vid = r["video_id"]
        base = r["storage_path"]
        original_path = os.path.join(abs_root, base, "original.webm")
        if not os.path.exists(original_path):
            continue
        job = await create_thumbnails_job(
            video_id=vid,
            src_path=original_path,
            out_base_path=os.path.join(abs_root, base),
        )
        jobs.append({"video_id": vid, "job_id": job.get("job_id")})

    return {"ok": True, "scheduled": jobs}