import hmac
import hashlib
import json
import os
import inspect
import tempfile
import shutil
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
from services.ytsprites.ytsprites_client_srv import submit_and_wait, create_thumbnails_job
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from utils.ytsprites.ytsprites_ut import prefix_sprite_paths, normalize_vtt
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

        # Read VTT rel from DB: asset type "thumbs_vtt"
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

        # Gather captions/*.vtt (local listing)
        storage_client: StorageClient = request.app.state.storage
        captions_rel_dir = os.path.join(storage_rel, "captions")
        captions_abs_dir = storage_client.to_abs(captions_rel_dir)
        captions_files: List[Dict[str, Optional[str]]] = []
        if os.path.isdir(captions_abs_dir):
            for name in sorted(os.listdir(captions_abs_dir)):
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
            "thumbs_vtt_url": thumbs_vtt_url,
            "sprites": sprite_urls,
            "captions_vtt_url": captions_vtt_url,
            "captions_lang": captions_lang,
            "storage_path": storage_rel,
            "captions_files": captions_files,
        }
    finally:
        await release_conn(conn)

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

        # Reset thumbnails/VTT state in DB
        await reset_thumbnails_state(conn, video_id)
    finally:
        await release_conn(conn)

    # ytsprites flow: submit -> wait -> save -> DB update
    try:
        storage_client: StorageClient = request.app.state.storage
        original_abs = storage_client.to_abs(os.path.join(storage_rel, "original.webm"))
        if not os.path.exists(original_abs):
            return JSONResponse({"ok": False, "error": "original_missing"}, status_code=404)

        video_id2, sprites, vtt_text = submit_and_wait(video_id, original_abs, (YTSPRITES_DEFAULT_MIME or "video/webm"))

        # bugfix - if subdir "sprites/" is lost
        vtt_patched = prefix_sprite_paths(vtt_text, prefix="sprites/")
        vtt_final = normalize_vtt(vtt_patched)

        # Save VTT
        rel_vtt = os.path.join(storage_rel, "sprites.vtt")
        abs_vtt = storage_client.to_abs(rel_vtt)
        try:
            with open(abs_vtt, "w", encoding="utf-8") as f:
                f.write(vtt_final or "")
        except Exception:
            try:
                with open(abs_vtt, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception:
                pass

        # Save sprites
        rel_sprite_dir = os.path.join(storage_rel, "sprites")
        abs_sprite_dir = storage_client.to_abs(rel_sprite_dir)
        try:
            os.makedirs(abs_sprite_dir, exist_ok=True)
        except Exception:
            pass

        rel_sprite_paths: List[str] = []
        for idx, (name, data) in enumerate(sprites, start=1):
            rel_sprite = os.path.join(rel_sprite_dir, name)
            abs_sprite = storage_client.to_abs(rel_sprite)
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


def _norm_sprite_rel(rel: str) -> str:
    s = str(rel or "").strip()
    s = s.lstrip("/")
    if not s:
        return s
    if not s.startswith("sprites/"):
        s = "sprites/" + s
    return s


def _rewrite_vtt_add_prefix(src_vtt_abs: str, dst_vtt_abs: str) -> None:
    """
    Rewrite sprites VTT so that image lines always include 'sprites/' prefix.
    Keeps timestamps lines unchanged, only normalizes the following reference line.
    """
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


@router.post("/internal/ytsprites/thumbnails/retry")
async def retry_thumbnails(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    """
    Regenerates sprites (thumbnail tiles) and VTT for a given video.

    Works in both local and remote storage modes:
    - local: operates directly on storage absolute paths
    - remote: downloads original to tmp, generates locally, then uploads sprites/VTT back to storage

    Ensures VTT references include 'sprites/' prefix. Upserts DB assets for VTT and sprites.
    """
    storage: StorageClient = request.app.state.storage

    conn = await get_conn()
    try:
        storage_rel = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
        if not storage_rel:
            raise HTTPException(status_code=404, detail="video_storage_not_found")

        original_rel = storage.join(storage_rel, "original.webm")
        original_abs_storage = storage.to_abs(original_rel)
        out_base_abs_storage = storage.to_abs(storage_rel)

        is_local_mode = os.path.exists(original_abs_storage)

        if is_local_mode:
            if not os.path.exists(original_abs_storage):
                raise HTTPException(status_code=404, detail="original_missing")
            job = await create_thumbnails_job(
                video_id=video_id,
                src_path=original_abs_storage,
                out_base_path=out_base_abs_storage,
                src_url=None,
                extra=None,
            )
            vtt_rel = job.get("vtt_rel")  # e.g., "sprites.vtt"
            sprites_rels = [ _norm_sprite_rel(r) for r in (job.get("sprites") or []) ]

            # Upsert VTT and sprites under consistent asset types
            if vtt_rel:
                vtt_rel_storage = storage.join(storage_rel, vtt_rel)
                await upsert_video_asset(conn, video_id, "thumbs_vtt", vtt_rel_storage)
            for idx, rel in enumerate(sprites_rels, start=1):
                await upsert_video_asset(conn, video_id, f"sprite:{idx}", storage.join(storage_rel, rel))
            await mark_thumbnails_ready(conn, video_id)

            return JSONResponse({
                "ok": True,
                "job_id": job.get("job_id"),
                "vtt_url": build_storage_url(storage.join(storage_rel, vtt_rel)) if vtt_rel else None,
                "sprites": [build_storage_url(storage.join(storage_rel, r)) for r in sprites_rels],
            })

        # Remote mode
        tmp_dir = tempfile.mkdtemp(prefix="ytms_")
        try:
            tmp_original_abs = os.path.join(tmp_dir, "original.webm")

            reader_ctx = storage.open_reader(original_rel)
            if inspect.isawaitable(reader_ctx):
                reader_ctx = await reader_ctx

            wrote_any = False
            try:
                if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
                    async for chunk in reader_ctx:
                        if chunk:
                            with open(tmp_original_abs, "ab") as lf:
                                lf.write(chunk)
                                wrote_any = True
                else:
                    for chunk in reader_ctx:
                        if chunk:
                            with open(tmp_original_abs, "ab") as lf:
                                lf.write(chunk)
                                wrote_any = True
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"download_failed: {e}")

            if not wrote_any or not os.path.exists(tmp_original_abs):
                raise HTTPException(status_code=404, detail="original_unavailable_remote")

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
            sprites_rels_local_raw: List[str] = job.get("sprites") or []
            sprites_rels_local: List[str] = [ _norm_sprite_rel(r) for r in sprites_rels_local_raw ]

            sprites_rel_dir = storage.join(storage_rel, "sprites")
            mkdirs_res = storage.mkdirs(sprites_rel_dir, exist_ok=True)
            if inspect.isawaitable(mkdirs_res):
                await mkdirs_res

            vtt_url = None

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

                    await upsert_video_asset(conn, video_id, "thumbs_vtt", vtt_rel_remote)
                    vtt_url = build_storage_url(vtt_rel_remote)

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

            # Upsert sprites in DB and mark ready
            for idx, rel in enumerate(uploaded_sprites, start=1):
                await upsert_video_asset(conn, video_id, f"sprite:{idx}", rel)
            await mark_thumbnails_ready(conn, video_id)

            return JSONResponse({
                "ok": True,
                "job_id": job.get("job_id"),
                "vtt_url": vtt_url,
                "sprites": [build_storage_url(rel) for rel in uploaded_sprites],
            })
        finally:
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass
    finally:
        await release_conn(conn)


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
async def ytsprites_thumbnails_backfill(request: Request, limit: int = 50):
    """
    Schedules regeneration via ytsprites for videos missing thumbnails.
    """
    conn = await get_conn()
    try:
        rows = await list_videos_needing_thumbnails(conn, limit=limit)
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    results = []
    for r in rows:
        vid = r["video_id"]
        base = r["storage_path"]
        original_abs = storage_client.to_abs(os.path.join(base, "original.webm"))
        if not os.path.exists(original_abs):
            continue

        try:
            video_id2, sprites, vtt_text = submit_and_wait(vid, original_abs, (YTSPRITES_DEFAULT_MIME or "video/webm"))

            target_dir_rel = os.path.join(base, "sprites")
            target_dir_abs = storage_client.to_abs(target_dir_rel)
            try:
                os.makedirs(target_dir_abs, exist_ok=True)
            except Exception:
                pass

            vtt_patched = prefix_sprite_paths(vtt_text, prefix="sprites/")
            vtt_final = normalize_vtt(vtt_patched)

            rel_vtt = os.path.join(base, "sprites.vtt")
            abs_vtt = storage_client.to_abs(rel_vtt)
            try:
                with open(abs_vtt, "w", encoding="utf-8") as f:
                    f.write(vtt_final or "")
            except Exception:
                try:
                    with open(abs_vtt, "w", encoding="utf-8") as f:
                        f.write("")
                except Exception:
                    pass

            rel_sprite_paths: List[str] = []
            for idx, (name, data) in enumerate(sprites, start=1):
                name_norm = name.lstrip("/")
                if not name_norm.startswith("sprites/"):
                    name_norm = "sprites/" + name_norm
                rel_sprite = os.path.join(base, name_norm)
                abs_sprite = storage_client.to_abs(rel_sprite)
                try:
                    with open(abs_sprite, "wb") as f:
                        f.write(data or b"")
                    rel_sprite_paths.append(rel_sprite)
                except Exception:
                    continue

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