import hmac
import hashlib
import json
import os
from typing import Any, Optional, Dict, List

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.ytsprites.ytsprites_cfg import (
    APP_STORAGE_WEB_PREFIX,
)
from config.config import settings
from config.ytstorage.ytstorage_remote_cfg import (
    STORAGE_REMOTE_ADDRESS,
    STORAGE_REMOTE_TOKEN,
)
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset
from db.assets_db import get_video_sprite_assets, get_thumbs_vtt_asset
from db.ytsprites.ytsprites_db import (
    fetch_video_storage_path,
    mark_thumbnails_ready,
    get_thumbnails_asset_path,
    get_thumbnails_flag,
    list_videos_needing_thumbnails,
    reset_thumbnails_state,
)
from db.videos_db import get_owned_video
from db.captions_db import get_video_captions_status
from services.ytsprites.ytsprites_client_srv import (
    create_job_storage_driven,
    watch_status,
    get_result,
    pick_ytsprites_addr,
)
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from utils.ytcms.ytcms_ut import get_active_cms_server

# --- Storage abstraction ---
from services.ytstorage.base_srv import StorageClient

router = APIRouter(tags=["ytsprites"])
templates = Jinja2Templates(directory="templates")


def _csrf_cookie_name() -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")


def _get_csrf_cookie(request: Request) -> str:
    return (request.cookies.get(_csrf_cookie_name()) or "").strip()


def _gen_csrf_token() -> str:
    import secrets
    return secrets.token_urlsafe(32)


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

        # captions listing via local filesystem is deprecated when ytstorage mandatory.
        assets = {
            "thumb_asset_path": thumb_rel,
            "thumb_url": thumb_url,
            "thumbs_vtt_url": thumbs_vtt_url,
            "sprites": sprite_urls,
            "captions_vtt_url": captions_vtt_url,
            "captions_lang": captions_lang,
            "storage_path": storage_rel,
            "captions_files": [],
        }
    finally:
        await release_conn(conn)

    active_sprites_server = pick_ytsprites_addr()
    active_cms_server = get_active_cms_server()
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
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
            "active_sprites_server": active_sprites_server,
            "active_cms_server": active_cms_server,
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
    """
    Deprecated handler retained for compatibility. Now routes to /internal/ytsprites/thumbnails/retry.
    """
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
        await reset_thumbnails_state(conn, video_id)
    finally:
        await release_conn(conn)

    # Frontend expects ok response; actual generation is invoked via /internal endpoint now.
    return JSONResponse({"ok": True, "queued": True})


@router.post("/internal/ytsprites/thumbnails/retry")
async def retry_thumbnails(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    """
    New flow:
    - yurtube does NOT download original.webm
    - yurtube calls ytsprites.CreateJob with (ytstorage addr + rel_path) and output dir
    - ytsprites downloads from ytstorage and uploads results back to ytstorage
    - yurtube updates DB assets from ytsprites.GetResult (paths)
    """
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
        await reset_thumbnails_state(conn, video_id)

        original_rel = f"{storage_rel}/original.webm".lstrip("/")

        # Create job
        job_id, job_server = create_job_storage_driven(
            video_id=video_id,
            source_storage_addr=STORAGE_REMOTE_ADDRESS,
            source_rel_path=original_rel,
            out_storage_addr=STORAGE_REMOTE_ADDRESS,
            out_base_rel_dir=storage_rel,
            video_mime="video/webm",
            filename="original.webm",
            storage_token=STORAGE_REMOTE_TOKEN,
        )

        # Wait for completion and fetch result
        watch_status(job_id, job_server)
        rep = get_result(job_id, job_server)

        if rep.state != rep.JOB_STATE_DONE:
            return JSONResponse(
                {"ok": False, "job_id": job_id, "state": int(rep.state), "error": rep.message or "failed"},
                status_code=500,
            )

        # Persist assets in DB (paths are already storage rel paths)
        if rep.vtt and rep.vtt.rel_path:
            await upsert_video_asset(conn, video_id, "thumbs_vtt", rep.vtt.rel_path)

        sprite_urls: List[str] = []
        for idx, art in enumerate(rep.sprites, start=1):
            if not art.rel_path:
                continue
            await upsert_video_asset(conn, video_id, f"sprite:{idx}", art.rel_path)
            sprite_urls.append(build_storage_url(art.rel_path))

        await mark_thumbnails_ready(conn, video_id)

        return JSONResponse(
            {
                "ok": True,
                "job_id": job_id,
                "vtt_url": build_storage_url(rep.vtt.rel_path) if rep.vtt and rep.vtt.rel_path else None,
                "sprites": sprite_urls,
            }
        )

    finally:
        await release_conn(conn)


@router.get("/internal/ytsprites/thumbnails/status")
async def ytsprites_thumbnails_status(video_id: str):
    """
    Polling endpoint used by UI: backed by DB (not by ytsprites service).
    """
    conn = await get_conn()
    try:
        asset_path = await get_thumbnails_asset_path(conn, video_id)
        ready_flag = await get_thumbnails_flag(conn, video_id)
        vtt_url = build_storage_url(asset_path) if asset_path else None
        return {"ok": True, "video_id": video_id, "ready": bool(ready_flag), "vtt_path": vtt_url}
    finally:
        await release_conn(conn)


@router.post("/internal/ytsprites/thumbnails/backfill")
async def ytsprites_thumbnails_backfill(request: Request, limit: int = 50):
    """
    Backfill: keep it simple for now — DB-driven list and sequential CreateJob+Wait.
    (Can be moved to a dedicated worker later.)
    """
    conn = await get_conn()
    try:
        rows = await list_videos_needing_thumbnails(conn, limit=limit)
    finally:
        await release_conn(conn)

    results = []
    for r in rows:
        vid = r["video_id"]
        storage_rel = (r.get("storage_path") or "").rstrip("/")
        if not storage_rel:
            results.append({"video_id": vid, "ok": False, "error": "missing_storage_path"})
            continue

        original_rel = f"{storage_rel}/original.webm".lstrip("/")
        try:
            job_id, job_server = create_job_storage_driven(
                video_id=vid,
                source_storage_addr=STORAGE_REMOTE_ADDRESS,
                source_rel_path=original_rel,
                out_storage_addr=STORAGE_REMOTE_ADDRESS,
                out_base_rel_dir=storage_rel,
                video_mime="video/webm",
                filename="original.webm",
                storage_token=STORAGE_REMOTE_TOKEN,
            )
            watch_status(job_id, job_server)
            rep = get_result(job_id, job_server)
            if rep.state != rep.JOB_STATE_DONE:
                results.append({"video_id": vid, "ok": False, "error": rep.message or "failed"})
                continue

            conn2 = await get_conn()
            try:
                if rep.vtt and rep.vtt.rel_path:
                    await upsert_video_asset(conn2, vid, "thumbs_vtt", rep.vtt.rel_path)
                for idx, art in enumerate(rep.sprites, start=1):
                    if art.rel_path:
                        await upsert_video_asset(conn2, vid, f"sprite:{idx}", art.rel_path)
                await mark_thumbnails_ready(conn2, vid)
            finally:
                await release_conn(conn2)

            results.append({"video_id": vid, "ok": True, "job_id": job_id})
        except Exception as e:
            results.append({"video_id": vid, "ok": False, "error": str(e)})

    return {"ok": True, "processed": results}