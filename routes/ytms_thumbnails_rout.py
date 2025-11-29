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
from db.assets_db import get_video_sprite_assets, get_thumbs_vtt_asset
from db.ytms_db import (
    fetch_video_storage_path,
    mark_thumbnails_ready,
    get_thumbnails_asset_path,
    get_thumbnails_flag,
    list_videos_needing_thumbnails,
    reset_thumbnails_state,
)
from db.videos_db import get_owned_video
from db.captions_db import get_video_captions_status
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

        storage_rel = owned["storage_path"].rstrip("/")

        thumb_rel = owned.get("thumb_asset_path")
        thumb_url = build_storage_url(thumb_rel) if thumb_rel else None

        sprite_paths_rel = await get_video_sprite_assets(conn, video_id)
        sprite_urls = [build_storage_url(p) for p in sprite_paths_rel]

        vtt_rel = await get_thumbs_vtt_asset(conn, video_id)
        thumbs_vtt_url = build_storage_url(vtt_rel) if vtt_rel else None

        captions_status = await get_video_captions_status(conn, video_id)
        captions_vtt_url = None
        captions_lang = None
        captions_primary_rel = None
        if captions_status and captions_status.get("captions_vtt"):
            captions_primary_rel = captions_status["captions_vtt"]
            captions_vtt_url = build_storage_url(captions_primary_rel)
            captions_lang = captions_status.get("captions_lang")

        # Gather all captions/*.vtt for video
        abs_root = getattr(settings, "STORAGE_ROOT", STORAGE_FS_ROOT)
        captions_dir = os.path.join(abs_root, storage_rel, "captions")
        captions_files: List[Dict[str, Optional[str]]] = []
        if os.path.isdir(captions_dir):
            for name in sorted(os.listdir(captions_dir)):
                if not name.lower().endswith(".vtt"):
                    continue
                rel_path = f"captions/{name}"
                captions_files.append({
                    "rel_vtt": rel_path,
                    "lang": None,
                })

        if captions_primary_rel:
            prefix = storage_rel + "/"
            rel_inside = captions_primary_rel
            if rel_inside.startswith(prefix):
                rel_inside = rel_inside[len(prefix):]
            if rel_inside.startswith("/"):
                rel_inside = rel_inside[1:]
            if rel_inside.startswith("captions/") and all(cf["rel_vtt"] != rel_inside for cf in captions_files):
                captions_files.insert(0, {
                    "rel_vtt": rel_inside,
                    "lang": None,
                })

        assets = {
            "thumb_asset_path": thumb_rel,
            "thumb_url": thumb_url,
            "thumbs_vtt": thumbs_vtt_url,
            "sprites": sprite_urls,
            "captions_vtt": captions_vtt_url,
            "captions_lang": captions_lang,
            "storage_path": storage_rel,
            "captions_files": captions_files,
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

    if "ok" not in job:
        if any(k in job for k in ("job_id", "job", "id")):
            job["ok"] = True
        else:
            job = {"ok": False, "error": "empty_job_response", "raw": job}

    return JSONResponse(job)


@router.get("/manage/ytms/status/{job_id}")
async def media_job_status(job_id: str) -> Any:
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
    return JSONResponse({"ok": False, "error": "not_implemented"}, status_code=501)


@router.post("/internal/ytms/thumbnails/callback")
async def ytms_thumbnails_callback(request: Request):
    body = await request.body()
    sig = request.headers.get("X-Signature", "").strip()
    calc = hmac.new(YTMS_CALLBACK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
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

    sprites_payload = payload.get("sprites") or []

    conn = await get_conn()
    try:
        storage_base = await fetch_video_storage_path(conn, video_id)
        if not storage_base:
            raise HTTPException(status_code=404, detail="storage_path_not_found")

        abs_root = getattr(settings, "STORAGE_ROOT", STORAGE_FS_ROOT)

        rel_vtt = os.path.join(storage_base, vtt_rel_path)
        vtt_abs = os.path.join(abs_root, rel_vtt)
        vtt_url = build_storage_url(rel_vtt)
        await upsert_video_asset(conn, video_id, "thumbs_vtt", rel_vtt)

        for sp in sprites_payload:
            rel = sp.get("path")
            idx = sp.get("index")
            if rel is None or idx is None:
                continue
            rel_sprite = os.path.join(storage_base, rel)
            await upsert_video_asset(conn, video_id, f"sprite:{idx}", rel_sprite)

        try:
            await mark_thumbnails_ready(conn, video_id)
        except Exception:
            pass

        return {
            "ok": True,
            "status": status,
            "asset_type": "thumbs_vtt",
            "path": vtt_url,
        }
    finally:
        await release_conn(conn)


@router.post("/internal/ytms/thumbnails/retry")
async def ytms_thumbnails_retry(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login_required")
    if not _validate_csrf(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        storage_base = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
        if not storage_base:
            raise HTTPException(status_code=404, detail="video_not_ready")

        await reset_thumbnails_state(conn, video_id)
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", STORAGE_FS_ROOT)
    original_path = os.path.join(abs_root, storage_base, "original.webm")
    if not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="original_missing")

    sprites_dir = os.path.join(abs_root, storage_base, "sprites")
    vtt_file = os.path.join(abs_root, storage_base, "sprites.vtt")
    if os.path.isdir(sprites_dir):
        for name in os.listdir(sprites_dir):
            try:
                os.remove(os.path.join(sprites_dir, name))
            except Exception:
                pass
        try:
            os.rmdir(sprites_dir)
        except Exception:
            pass
    if os.path.exists(vtt_file):
        try:
            os.remove(vtt_file)
        except Exception:
            pass

    job = await create_thumbnails_job(
        video_id=video_id,
        src_path=original_path,
        out_base_path=os.path.join(abs_root, storage_base),
        extra=None,
    )
    return {"ok": True, "job": job, "reset": True}


@router.get("/internal/ytms/thumbnails/status")
async def ytms_thumbnails_status(video_id: str):
    conn = await get_conn()
    try:
        asset_path = await get_thumbnails_asset_path(conn, video_id)
        ready_flag = await get_thumbnails_flag(conn, video_id)
        vtt_url = None
        if asset_path:
            vtt_url = build_storage_url(asset_path)
        return {
            "ok": True,
            "video_id": video_id,
            "ready": bool(ready_flag),
            "vtt_path": vtt_url,
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