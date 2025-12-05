import hmac
import hashlib
import json
import os
from typing import Any, Optional, Dict, List

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.ytsprites.ytsprites_cfg import (
    YTSPRITES_DEFAULT_MIME,
    APP_STORAGE_FS_ROOT,
    APP_STORAGE_WEB_PREFIX,
)
from config.config import settings
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
from services.ytsprites.ytsprites_client_srv import submit_and_wait
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

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


def _fs_to_web_path(abs_path: str) -> str:
    root_norm = (APP_STORAGE_FS_ROOT or "/var/www/yurtube/storage").rstrip("/")
    if abs_path.startswith(root_norm):
        rel = abs_path[len(root_norm):]
        if not rel.startswith("/"):
            rel = "/" + rel
        return (APP_STORAGE_WEB_PREFIX or "/storage").rstrip("/") + rel
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
        abs_root = getattr(settings, "STORAGE_ROOT", APP_STORAGE_FS_ROOT)
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
    """
    Deprecated handler retained for compatibility. Now routes to ytsprites flow.
    Returns JSON for old JS clients; new clients use /internal/ytsprites/thumbnails/retry directly.
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
        abs_root = getattr(settings, "STORAGE_ROOT", APP_STORAGE_FS_ROOT)
        src_path = os.path.join(abs_root, storage_rel, "original.webm")
        if not os.path.exists(src_path):
            return JSONResponse({"ok": False, "error": "original_missing"}, status_code=404)

        # Reset thumbnails/VTT state in DB
        await reset_thumbnails_state(conn, video_id)
    finally:
        await release_conn(conn)

    # ytsprites flow: submit -> wait -> save -> DB update
    try:
        video_id2, sprites, vtt_text = submit_and_wait(video_id, src_path, (YTSPRITES_DEFAULT_MIME or "video/webm"))

        abs_root = getattr(settings, "STORAGE_ROOT", APP_STORAGE_FS_ROOT)

        # Save VTT
        rel_vtt = os.path.join(storage_rel, "sprites.vtt")
        abs_vtt = os.path.join(abs_root, rel_vtt)
        try:
            with open(abs_vtt, "w", encoding="utf-8") as f:
                f.write(vtt_text or "")
        except Exception:
            try:
                with open(abs_vtt, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception:
                pass

        # Save sprites
        rel_sprite_dir = os.path.join(storage_rel, "sprites")
        abs_sprite_dir = os.path.join(abs_root, rel_sprite_dir)
        try:
            os.makedirs(abs_sprite_dir, exist_ok=True)
        except Exception:
            pass

        rel_sprite_paths: List[str] = []
        for idx, (name, data) in enumerate(sprites, start=1):
            rel_sprite = os.path.join(rel_sprite_dir, name)
            abs_sprite = os.path.join(abs_root, rel_sprite)
            try:
                with open(abs_sprite, "wb") as f:
                    f.write(data or b"")
                rel_sprite_paths.append(rel_sprite)
            except Exception:
                continue

        # DB update: store RELATIVE paths, asset types by index
        conn = await get_conn()
        try:
            await upsert_video_asset(conn, video_id, "thumbs_vtt", rel_vtt)
            for idx, rel_path in enumerate(rel_sprite_paths, start=1):
                await upsert_video_asset(conn, video_id, f"sprite:{idx}", rel_path)
            await mark_thumbnails_ready(conn, video_id)
        finally:
            await release_conn(conn)

        return JSONResponse({"ok": True, "job_id": "ytsprites-local", "saved": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/internal/ytsprites/thumbnails/retry")
async def ytsprites_thumbnails_retry(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    """
    Main handler to (re)generate sprites & VTT using ytsprites service.
    Behavior:
    - validates auth and CSRF
    - resets DB state and removes old files
    - calls gRPC service (submit_and_wait)
    - writes new files to storage
    - updates DB assets (RELATIVE paths)
    - marks thumbnails_ready = TRUE
    - redirects back to the page
    """
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

        # reset DB flags and asset records
        await reset_thumbnails_state(conn, video_id)
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", APP_STORAGE_FS_ROOT)
    original_path = os.path.join(abs_root, storage_base, "original.webm")
    if not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="original_missing")

    # delete old files
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

    # run gRPC flow and persist results
    video_id2, sprites, vtt_text = submit_and_wait(video_id, original_path, (YTSPRITES_DEFAULT_MIME or "video/webm"))

    # save files
    target_dir_rel = os.path.join(storage_base, "sprites")
    target_dir_abs = os.path.join(abs_root, target_dir_rel)
    try:
        os.makedirs(target_dir_abs, exist_ok=True)
    except Exception:
        pass

    rel_vtt = os.path.join(storage_base, "sprites.vtt")
    abs_vtt = os.path.join(abs_root, rel_vtt)
    try:
        with open(abs_vtt, "w", encoding="utf-8") as f:
            f.write(vtt_text or "")
    except Exception:
        try:
            with open(abs_vtt, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass

    rel_sprite_paths: List[str] = []
    for idx, (name, data) in enumerate(sprites, start=1):
        rel_sprite = os.path.join(target_dir_rel, name)
        abs_sprite = os.path.join(abs_root, rel_sprite)
        try:
            with open(abs_sprite, "wb") as f:
                f.write(data or b"")
            rel_sprite_paths.append(rel_sprite)
        except Exception:
            continue

    # update DB: relative paths, types sprite:1..N
    conn = await get_conn()
    try:
        await upsert_video_asset(conn, video_id, "thumbs_vtt", rel_vtt)
        for idx, rel_path in enumerate(rel_sprite_paths, start=1):
            await upsert_video_asset(conn, video_id, f"sprite:{idx}", rel_path)
        await mark_thumbnails_ready(conn, video_id)
    finally:
        await release_conn(conn)

    # redirect back
    ref = request.headers.get("referer")
    if ref:
        return RedirectResponse(ref, status_code=303)
    return HTMLResponse("<html><body><p>OK</p></body></html>", status_code=200)


@router.get("/internal/ytsprites/thumbnails/status")
async def ytsprites_thumbnails_status(video_id: str):
    """
    Simple status endpoint compatible with old polling JS:
    Reports readiness based on DB flags and VTT presence.
    """
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


@router.post("/internal/ytsprites/thumbnails/backfill")
async def ytsprites_thumbnails_backfill(limit: int = 50):
    """
    Schedules regeneration via ytsprites for videos missing thumbnails.
    """
    conn = await get_conn()
    try:
        rows = await list_videos_needing_thumbnails(conn, limit=limit)
    finally:
        await release_conn(conn)

    abs_root = getattr(settings, "STORAGE_ROOT", APP_STORAGE_FS_ROOT)
    results = []
    for r in rows:
        vid = r["video_id"]
        base = r["storage_path"]
        original_path = os.path.join(abs_root, base, "original.webm")
        if not os.path.exists(original_path):
            continue

        try:
            video_id2, sprites, vtt_text = submit_and_wait(vid, original_path, (YTSPRITES_DEFAULT_MIME or "video/webm"))

            # save files
            target_dir_rel = os.path.join(base, "sprites")
            target_dir_abs = os.path.join(abs_root, target_dir_rel)
            try:
                os.makedirs(target_dir_abs, exist_ok=True)
            except Exception:
                pass

            rel_vtt = os.path.join(base, "sprites.vtt")
            abs_vtt = os.path.join(abs_root, rel_vtt)
            try:
                with open(abs_vtt, "w", encoding="utf-8") as f:
                    f.write(vtt_text or "")
            except Exception:
                try:
                    with open(abs_vtt, "w", encoding="utf-8") as f:
                        f.write("")
                except Exception:
                    pass

            rel_sprite_paths: List[str] = []
            for idx, (name, data) in enumerate(sprites, start=1):
                rel_sprite = os.path.join(target_dir_rel, name)
                abs_sprite = os.path.join(abs_root, rel_sprite)
                try:
                    with open(abs_sprite, "wb") as f:
                        f.write(data or b"")
                    rel_sprite_paths.append(rel_sprite)
                except Exception:
                    continue

            # update DB (relative paths)
            conn = await get_conn()
            try:
                await upsert_video_asset(conn, vid, "thumbs_vtt", rel_vtt)
                for idx, rel_path in enumerate(rel_sprite_paths, start=1):
                    await upsert_video_asset(conn, vid, f"sprite:{idx}", rel_path)
                await mark_thumbnails_ready(conn, vid)
            finally:
                await release_conn(conn)

            results.append({"video_id": vid, "ok": True})
        except Exception as e:
            results.append({"video_id": vid, "ok": False, "error": str(e)})

    return {"ok": True, "processed": results}