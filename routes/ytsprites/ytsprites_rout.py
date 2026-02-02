import os
import inspect
import tempfile
import shutil
import asyncio
from typing import Any, Optional, Dict, List

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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
from services.ytsprites.ytsprites_client_srv import create_thumbnails_job, pick_ytsprites_addr
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from utils.ytcms.ytcms_ut import get_active_cms_server

from services.ytstorage.base_srv import StorageClient

router = APIRouter(tags=["ytsprites"])
templates = Jinja2Templates(directory="templates")

_video_locks: Dict[str, asyncio.Lock] = {}
_thumbs_sem = asyncio.Semaphore(1)  # global limiter: only 1 heavy job per process


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


def _norm_sprite_rel(rel: str) -> str:
    s = str(rel or "").strip().lstrip("/")
    if not s:
        return s
    if not s.startswith("sprites/"):
        s = "sprites/" + s
    return s


def _rewrite_vtt_add_prefix(src_vtt_abs: str, dst_vtt_abs: str) -> None:
    try:
        with open(src_vtt_abs, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception:
        return

    out: List[str] = []
    i = 0
    ln = len(lines)
    while i < ln:
        line = (lines[i] or "").strip()
        out.append(line)
        if "-->" in line:
            if i + 1 < ln:
                ref = (lines[i + 1] or "").strip()
                if "#xywh=" in ref:
                    p, h = ref.split("#xywh=", 1)
                    p = _norm_sprite_rel(p)
                    out.append(p + "#xywh=" + h)
                else:
                    out.append(_norm_sprite_rel(ref))
                i += 2
                continue
        i += 1

    try:
        with open(dst_vtt_abs, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
    except Exception:
        pass


async def _download_original_with_retries(
    storage: StorageClient,
    original_rel: str,
    tmp_original_abs: str,
    *,
    retries: int = 4,
    sleep_base_sec: float = 2.0,
) -> None:
    last_err = None
    part = tmp_original_abs + ".part"

    for attempt in range(1, retries + 1):
        try:
            try:
                if os.path.exists(part):
                    os.remove(part)
            except Exception:
                pass

            reader_ctx = storage.open_reader(original_rel)
            if inspect.isawaitable(reader_ctx):
                reader_ctx = await reader_ctx

            bytes_written = 0
            with open(part, "wb") as lf:
                if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
                    async for chunk in reader_ctx:
                        if not chunk:
                            continue
                        b = bytes(chunk)
                        lf.write(b)
                        bytes_written += len(b)
                else:
                    for chunk in reader_ctx:
                        if not chunk:
                            continue
                        lf.write(chunk)
                        bytes_written += len(chunk)

            if bytes_written <= 0:
                raise RuntimeError("download_wrote_nothing")

            os.replace(part, tmp_original_abs)
            print(f"[YTSPRITES][DL] OK rel={original_rel} bytes={bytes_written} attempt={attempt}/{retries}")
            return

        except Exception as e:
            last_err = e
            print(f"[YTSPRITES][DL] FAIL rel={original_rel} attempt={attempt}/{retries} err={e!r}")
            try:
                if os.path.exists(part):
                    os.remove(part)
            except Exception:
                pass
            await asyncio.sleep(min(sleep_base_sec * attempt, 10.0))

    raise RuntimeError(f"download_failed after {retries} attempts: {last_err!r}")


async def _persist_assets_and_mark_ready(
    video_id: str,
    storage_rel: str,
    vtt_rel: Optional[str],
    sprites_rels: List[str],
) -> None:
    conn = await get_conn()
    try:
        if vtt_rel:
            await upsert_video_asset(conn, video_id, "thumbs_vtt", vtt_rel)
        for idx, rel in enumerate(sprites_rels, start=1):
            await upsert_video_asset(conn, video_id, f"sprite:{idx}", rel)
        await mark_thumbnails_ready(conn, video_id)
    finally:
        await release_conn(conn)


async def _run_thumbnails_job(request: Request, video_id: str) -> None:
    storage: StorageClient = request.app.state.storage

    # Acquire global limiter so we don't kill DB pool / CPU / IO.
    async with _thumbs_sem:
        try:
            # Fetch storage_rel using a short-lived DB connection
            conn = await get_conn()
            try:
                storage_rel = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
            finally:
                await release_conn(conn)

            if not storage_rel:
                raise RuntimeError("video_storage_not_found")

            original_rel = storage.join(storage_rel, "original.webm")
            original_abs_storage = storage.to_abs(original_rel)
            out_base_abs_storage = storage.to_abs(storage_rel)

            is_local_mode = os.path.exists(original_abs_storage)

            if is_local_mode:
                job = await create_thumbnails_job(
                    video_id=video_id,
                    src_path=original_abs_storage,
                    out_base_path=out_base_abs_storage,
                    src_url=None,
                    extra=None,
                )
                vtt_rel_local = job.get("vtt_rel")  # "sprites.vtt"
                sprites_rels_local = [_norm_sprite_rel(r) for r in (job.get("sprites") or [])]

                vtt_rel_storage = storage.join(storage_rel, vtt_rel_local) if vtt_rel_local else None
                sprites_rels_storage = [storage.join(storage_rel, r) for r in sprites_rels_local]

                await _persist_assets_and_mark_ready(video_id, storage_rel, vtt_rel_storage, sprites_rels_storage)
                return

            # Remote mode
            tmp_dir = tempfile.mkdtemp(prefix="ytms_")
            try:
                tmp_original_abs = os.path.join(tmp_dir, "original.webm")
                await _download_original_with_retries(storage, original_rel, tmp_original_abs, retries=4)

                tmp_out_abs = os.path.join(tmp_dir, "out")
                os.makedirs(tmp_out_abs, exist_ok=True)

                job = await create_thumbnails_job(
                    video_id=video_id,
                    src_path=tmp_original_abs,
                    out_base_path=tmp_out_abs,
                    src_url=None,
                    extra=None,
                )

                vtt_rel_local = job.get("vtt_rel")
                sprites_rels_local = [_norm_sprite_rel(r) for r in (job.get("sprites") or [])]

                # Ensure remote dirs
                sprites_rel_dir = storage.join(storage_rel, "sprites")
                mkdirs_res = storage.mkdirs(sprites_rel_dir, exist_ok=True)
                if inspect.isawaitable(mkdirs_res):
                    await mkdirs_res

                vtt_rel_remote: Optional[str] = None
                if vtt_rel_local:
                    vtt_abs_local_orig = os.path.join(tmp_out_abs, vtt_rel_local)
                    if os.path.exists(vtt_abs_local_orig):
                        vtt_abs_local_norm = os.path.join(tmp_out_abs, "sprites.vtt")
                        _rewrite_vtt_add_prefix(vtt_abs_local_orig, vtt_abs_local_norm)
                        vtt_upload_abs = vtt_abs_local_norm if os.path.exists(vtt_abs_local_norm) else vtt_abs_local_orig

                        vtt_rel_remote = storage.join(storage_rel, "sprites.vtt")
                        wctx_vtt = storage.open_writer(vtt_rel_remote, overwrite=True)
                        if inspect.isawaitable(wctx_vtt):
                            wctx_vtt = await wctx_vtt
                        if hasattr(wctx_vtt, "__aenter__"):
                            async with wctx_vtt as f:
                                with open(vtt_upload_abs, "rb") as lf:
                                    while True:
                                        ch = lf.read(1024 * 1024)
                                        if not ch:
                                            break
                                        wr = f.write(ch)
                                        if inspect.isawaitable(wr):
                                            await wr
                        else:
                            with wctx_vtt as f:
                                with open(vtt_upload_abs, "rb") as lf:
                                    while True:
                                        ch = lf.read(1024 * 1024)
                                        if not ch:
                                            break
                                        f.write(ch)

                uploaded_sprites: List[str] = []
                for rel_local in sprites_rels_local:
                    abs_local = os.path.join(tmp_out_abs, rel_local)
                    if not os.path.isfile(abs_local):
                        fallback_abs = os.path.join(tmp_out_abs, "sprites", os.path.basename(rel_local))
                        if os.path.isfile(fallback_abs):
                            abs_local = fallback_abs
                        else:
                            continue

                    remote_rel = storage.join(storage_rel, rel_local)
                    wctx_sp = storage.open_writer(remote_rel, overwrite=True)
                    if inspect.isawaitable(wctx_sp):
                        wctx_sp = await wctx_sp
                    if hasattr(wctx_sp, "__aenter__"):
                        async with wctx_sp as f:
                            with open(abs_local, "rb") as lf:
                                while True:
                                    ch = lf.read(1024 * 1024)
                                    if not ch:
                                        break
                                    wr = f.write(ch)
                                    if inspect.isawaitable(wr):
                                        await wr
                    else:
                        with wctx_sp as f:
                            with open(abs_local, "rb") as lf:
                                while True:
                                    ch = lf.read(1024 * 1024)
                                    if not ch:
                                        break
                                    f.write(ch)

                    uploaded_sprites.append(remote_rel)

                await _persist_assets_and_mark_ready(video_id, storage_rel, vtt_rel_remote, uploaded_sprites)

            finally:
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass

        except Exception as e:
            print(f"[YTSPRITES] thumbnails job failed video_id={video_id}: {e!r}")


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
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
            "active_sprites_server": active_sprites_server,
            "active_cms_server": active_cms_server,
        },
    )
    if not _get_csrf_cookie(request):
        resp.set_cookie(_csrf_cookie_name(), csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return resp


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
        await reset_thumbnails_state(conn, video_id)
    finally:
        await release_conn(conn)

    lock = _video_locks.setdefault(video_id, asyncio.Lock())
    if lock.locked():
        return JSONResponse({"ok": True, "queued": True, "already_running": True})

    async def _bg():
        async with lock:
            await _run_thumbnails_job(request, video_id)

    asyncio.create_task(_bg())
    return JSONResponse({"ok": True, "queued": True})


@router.get("/internal/ytsprites/thumbnails/status")
async def ytsprites_thumbnails_status(video_id: str):
    conn = await get_conn()
    try:
        asset_path = await get_thumbnails_asset_path(conn, video_id)
        ready_flag = await get_thumbnails_flag(conn, video_id)
        vtt_url = build_storage_url(asset_path) if asset_path else None
        return {
            "ok": True,
            "video_id": video_id,
            "ready": bool(ready_flag),
            "vtt_path": vtt_url,
        }
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
        lock = _video_locks.setdefault(vid, asyncio.Lock())
        if lock.locked():
            results.append({"video_id": vid, "ok": True, "queued": True, "already_running": True})
            continue

        async def _bg(video_id_local: str, lk: asyncio.Lock):
            async with lk:
                await _run_thumbnails_job(request, video_id_local)

        asyncio.create_task(_bg(vid, lock))
        results.append({"video_id": vid, "ok": True, "queued": True})

    return {"ok": True, "processed": results}