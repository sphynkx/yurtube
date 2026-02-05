import os
import time
import asyncio
from typing import Any, Optional, Dict, List

from fastapi import APIRouter, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from config.ytstorage.ytstorage_cfg import (
    YTSTORAGE_GRPC_ADDRESS,
    YTSTORAGE_GRPC_TOKEN,
)
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset, get_video_sprite_assets, get_thumbs_vtt_asset
from db.ytsprites.ytsprites_db import (
    mark_thumbnails_ready,
    get_thumbnails_asset_path,
    get_thumbnails_flag,
    list_videos_needing_thumbnails,
    reset_thumbnails_state,
)
from db.videos_db import get_owned_video
from db.ytcms.captions_db import get_video_captions_status
from services.ytsprites.ytsprites_client_srv import (
    create_job_storage_driven,
    watch_status,
    wait_result_done,
    pick_ytsprites_addr,
    pb,
)
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from utils.ytcms.ytcms_ut import get_active_cms_server

from services.ytstorage.base_srv import StorageClient

router = APIRouter(tags=["ytsprites"])
templates = Jinja2Templates(directory="templates")

_YTSPRITES_PROGRESS: Dict[str, Dict[str, Any]] = {}
_PROGRESS_TTL_SEC = 6 * 3600


def _now() -> float:
    return time.time()


def _set_progress(video_id: str, data: Dict[str, Any]) -> None:
    d = dict(data)
    d["ts"] = _now()
    _YTSPRITES_PROGRESS[video_id] = d


def _get_progress(video_id: str) -> Optional[Dict[str, Any]]:
    d = _YTSPRITES_PROGRESS.get(video_id)
    if not d:
        return None
    if (_now() - float(d.get("ts", 0.0))) > _PROGRESS_TTL_SEC:
        try:
            del _YTSPRITES_PROGRESS[video_id]
        except Exception:
            pass
        return None
    return d


def _clear_progress(video_id: str) -> None:
    try:
        del _YTSPRITES_PROGRESS[video_id]
    except Exception:
        pass


def _is_final_state(state: int) -> bool:
    return int(state) in (int(pb.JOB_STATE_DONE), int(pb.JOB_STATE_FAILED), int(pb.JOB_STATE_CANCELED))


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
            "storage_public_base_url": getattr(settings, "YTSTORAGE_PUBLIC_BASE_URL", None),
            "active_sprites_server": active_sprites_server,
            "active_cms_server": active_cms_server,
        },
    )
    if not _get_csrf_cookie(request):
        resp.set_cookie(_csrf_cookie_name(), csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return resp


@router.get("/internal/ytsprites/thumbnails/progress")
async def ytsprites_thumbnails_progress(video_id: str = Query(...)) -> Any:
    st = _get_progress(video_id)
    if not st:
        return {"ok": True, "active": False}
    return {"ok": True, "active": True, **st}


def _start_watch_task(video_id: str, job_id: str, job_server: str) -> None:
    def _on_update(item: Dict[str, Any]) -> None:
        _set_progress(
            video_id,
            {
                "job_id": job_id,
                "job_server": job_server,
                "state": int(item.get("state") or 0),
                "percent": int(item.get("percent") if item.get("percent") is not None else -1),
                "message": str(item.get("message") or ""),
                "bytes_processed": int(item.get("bytes_processed") or 0),
            },
        )

    async def _runner():
        cur = _get_progress(video_id)
        if cur and not _is_final_state(int(cur.get("state") or 0)):
            return

        _set_progress(
            video_id,
            {
                "job_id": job_id,
                "job_server": job_server,
                "state": int(pb.JOB_STATE_QUEUED),
                "percent": 0,
                "message": "Queued",
            },
        )
        try:
            await asyncio.to_thread(watch_status, job_id, job_server, _on_update)
        except Exception as e:
            _set_progress(
                video_id,
                {
                    "job_id": job_id,
                    "job_server": job_server,
                    "state": int(pb.JOB_STATE_FAILED),
                    "percent": 0,
                    "message": f"watch failed: {e}",
                },
            )

    asyncio.create_task(_runner())


@router.post("/internal/ytsprites/thumbnails/retry")
async def retry_thumbnails(
    request: Request,
    video_id: str = Form(...),
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

        cur = _get_progress(video_id)
        if cur and not _is_final_state(int(cur.get("state") or 0)):
            return JSONResponse(
                {
                    "ok": True,
                    "already_running": True,
                    "job_id": cur.get("job_id"),
                    "state": int(cur.get("state") or 0),
                    "percent": int(cur.get("percent") or 0),
                    "message": cur.get("message") or "",
                }
            )

        ready_flag = await get_thumbnails_flag(conn, video_id)
        existing_vtt = await get_thumbnails_asset_path(conn, video_id)
        if ready_flag and existing_vtt:
            return JSONResponse({"ok": True, "already_ready": True})

        storage_rel = owned["storage_path"].rstrip("/")

        await reset_thumbnails_state(conn, video_id)
        _clear_progress(video_id)

        original_rel = f"{storage_rel}/original.webm".lstrip("/")

        job_id, job_server = create_job_storage_driven(
            video_id=video_id,
            source_storage_addr=YTSTORAGE_GRPC_ADDRESS,
            source_rel_path=original_rel,
            out_storage_addr=YTSTORAGE_GRPC_ADDRESS,
            out_base_rel_dir=storage_rel,
            video_mime="video/webm",
            filename="original.webm",
            storage_token=YTSTORAGE_GRPC_TOKEN,
        )

        _start_watch_task(video_id, job_id, job_server)

        rep = await asyncio.to_thread(wait_result_done, job_id, job_server, 1800.0, 1.0)

        if rep.state != pb.JOB_STATE_DONE:
            _set_progress(
                video_id,
                {
                    "job_id": job_id,
                    "job_server": job_server,
                    "state": int(rep.state),
                    "percent": -1,
                    "message": rep.message or "failed",
                },
            )
            return JSONResponse(
                {"ok": False, "job_id": job_id, "state": int(rep.state), "error": rep.message or "failed"},
                status_code=500,
            )

        if rep.vtt and rep.vtt.rel_path:
            await upsert_video_asset(conn, video_id, "thumbs_vtt", rep.vtt.rel_path)

        for idx, art in enumerate(rep.sprites, start=1):
            if art.rel_path:
                await upsert_video_asset(conn, video_id, f"sprite:{idx}", art.rel_path)

        await mark_thumbnails_ready(conn, video_id)

        _set_progress(video_id, {"job_id": job_id, "job_server": job_server, "state": int(pb.JOB_STATE_DONE), "percent": 100, "message": "Done"})

        return JSONResponse({"ok": True, "job_id": job_id})
    finally:
        await release_conn(conn)


@router.get("/internal/ytsprites/thumbnails/status")
async def ytsprites_thumbnails_status(video_id: str):
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

        cur = _get_progress(vid)
        if cur and not _is_final_state(int(cur.get("state") or 0)):
            results.append({"video_id": vid, "ok": True, "already_running": True, "job_id": cur.get("job_id")})
            continue

        original_rel = f"{storage_rel}/original.webm".lstrip("/")
        try:
            job_id, job_server = create_job_storage_driven(
                video_id=vid,
                source_storage_addr=YTSTORAGE_GRPC_ADDRESS,
                source_rel_path=original_rel,
                out_storage_addr=YTSTORAGE_GRPC_ADDRESS,
                out_base_rel_dir=storage_rel,
                video_mime="video/webm",
                filename="original.webm",
                storage_token=YTSTORAGE_GRPC_TOKEN,
            )

            _start_watch_task(vid, job_id, job_server)

            rep = await asyncio.to_thread(wait_result_done, job_id, job_server, 1800.0, 1.0)
            if rep.state != pb.JOB_STATE_DONE:
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