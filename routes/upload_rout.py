import os
import inspect
import time
import shutil
import subprocess
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset
from db.categories_db import category_exists, list_categories
from db.subscriptions_db import count_subscribers
from db.videos_db import (
    create_video,
    delete_video,
    get_owned_video,
    list_my_videos,
    set_video_ready,
    delete_video_by_owner,
)
from db.ytconvert.ytconvert_jobs_db import create_ytconvert_job

from services.ytsprites.ytsprites_client_srv import create_thumbnails_job
from db.ytsprites.ytsprites_db import fetch_video_storage_path

from services.ffmpeg_srv import (
    async_generate_thumbnails,
    pick_thumbnail_offsets,
    async_probe_duration_seconds,
    async_generate_animated_preview,
)
from services.search.indexer_srch import fire_and_forget_reindex, delete_from_index
from utils.idgen_ut import gen_id
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from db.comments.root_db import delete_all_comments_for_video

from services.ytcms.captions_generation import generate_captions
from db.captions_db import set_video_captions

# --- Storage abstraction ---
from services.ytstorage.base_srv import StorageClient
from utils.ytstorage.path_ut import build_video_storage_rel

# --- ytconvert (stage 0) ---
from services.ytconvert.ytconvert_runner_srv import schedule_ytconvert_job
from utils.ytconvert.variants_ut import compute_suggested_variants, expand_requested_variant_ids


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ---------- CSRF (multipart route-level) ----------

def _cookie_name() -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")


def _csrf_cookie(request: Request) -> str:
    return (request.cookies.get(_cookie_name()) or "").strip()


def _same_origin(request: Request) -> bool:
    origin = (request.headers.get("origin") or request.headers.get("referer") or "").strip()
    if not origin:
        return False
    try:
        from urllib.parse import urlparse
        o = urlparse(origin)
        host_hdr = request.headers.get("host") or ""
        scheme = request.url.scheme
        return f"{scheme}://{host_hdr}".lower() == f"{o.scheme}://{o.netloc}".lower()
    except Exception:
        return False


def _validate_csrf_multipart(request: Request, supplied_token: str) -> bool:
    cookie_tok = _csrf_cookie(request)
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    form_tok = (supplied_token or "").strip()
    token = form_tok or header_tok or qs_tok
    if not cookie_tok or not token:
        return False
    try:
        import secrets as _sec
        return _sec.compare_digest(cookie_tok, token)
    except Exception:
        return False


# ---------- Helpers ----------

def _fallback_title(file: UploadFile) -> str:
    base = (file.filename or "").strip()
    if base:
        name, _ = os.path.splitext(base)
        if name.strip():
            return name.strip()[:200]
    return "Video " + datetime.utcnow().strftime("%Y-%m-%d %H:%M")


def _bg_rm_rf(path: str) -> None:
    try:
        cmd = f'nohup rm -rf -- "{path}" >/dev/null 2>&1 &'
        subprocess.Popen(["/bin/sh", "-c", cmd],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         close_fds=True)
    except Exception:
        pass


async def _bg_delete_index(video_id: str) -> None:
    try:
        await delete_from_index(video_id)
    except Exception as e:
        print(f"[ERROR] Failed to delete from index: {e}")


async def _bg_delete_comments(video_id: str, timeout_sec: float = 5.0) -> None:
    try:
        await asyncio.wait_for(delete_all_comments_for_video(video_id), timeout=timeout_sec)
    except asyncio.TimeoutError:
        print(f"[ERROR] Timeout occurred while deleting comments for video_id {video_id}")
    except Exception as e:
        print(f"[ERROR] Failed to delete comments: {e}")


async def _bg_cleanup_after_delete(storage_client: StorageClient, storage_rel: str, video_id: str) -> None:
    try:
        print(f"[DEBUG] Starting cleanup for video folder: {storage_rel}")
        print(f"[DEBUG] Calling remove on storage client with: rel_path={storage_rel}, recursive=True")
        await storage_client.remove(storage_rel, recursive=True)
        print(f"[DEBUG] Cleanup successfully completed for video folder: {storage_rel}")

        print(f"[DEBUG] Deleting index for video_id={video_id}")
        await _bg_delete_index(video_id)
        print(f"[DEBUG] Index deletion completed for video_id={video_id}")

        print(f"[DEBUG] Deleting comments for video_id={video_id}")
        await _bg_delete_comments(video_id, timeout_sec=5.0)
        print(f"[DEBUG] Comment deletion completed for video_id={video_id}")

    except Exception as e:
        print(f"[ERROR] Cleanup failed for video_id={video_id}: {e}")


async def _probe_basic_video_info_ffprobe(abs_path: str) -> Dict[str, Any]:
    """
    Stage-0 helper: get width/height/codec/bitrate via ffprobe.
    Keeps upload route self-contained (no DB changes yet).

    Returns:
      {"width": int, "height": int, "vcodec": str, "acodec": str, "bitrate": int}
    """
    loop = asyncio.get_running_loop()

    def _run() -> Dict[str, Any]:
        import json as _json

        cmd = [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            abs_path,
        ]
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            data = _json.loads(out.decode("utf-8", "replace") or "{}")
        except Exception:
            return {"width": 0, "height": 0, "vcodec": "", "acodec": "", "bitrate": 0}

        width = 0
        height = 0
        vcodec = ""
        acodec = ""

        streams = data.get("streams") or []
        if isinstance(streams, list):
            # pick first video stream
            for s in streams:
                if not isinstance(s, dict):
                    continue
                if (s.get("codec_type") or "") == "video":
                    width = int(s.get("width") or 0)
                    height = int(s.get("height") or 0)
                    vcodec = str(s.get("codec_name") or "")
                    break
            # pick first audio stream
            for s in streams:
                if not isinstance(s, dict):
                    continue
                if (s.get("codec_type") or "") == "audio":
                    acodec = str(s.get("codec_name") or "")
                    break

        fmt = data.get("format") or {}
        bitrate = 0
        try:
            bitrate = int(fmt.get("bit_rate") or 0)
        except Exception:
            bitrate = 0

        return {"width": width, "height": height, "vcodec": vcodec, "acodec": acodec, "bitrate": bitrate}

    return await loop.run_in_executor(None, _run)


# ---------- Manage ----------

@router.get("/manage", response_class=HTMLResponse)
async def manage_home(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        rows = await list_my_videos(conn, user["user_uid"])
        subs_count = await count_subscribers(conn, user["user_uid"])
    finally:
        await release_conn(conn)

    videos: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        tap = d.get("thumb_asset_path")
        d["thumb_url"] = build_storage_url(tap) if tap else None
        videos.append(d)

    csrf_token = _csrf_cookie(request)

    return templates.TemplateResponse(
        "manage/my_videos.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "current_user": user,
            "videos": videos,
            "subscribers_count": subs_count,
            "csrf_token": csrf_token,
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/manage/delete")
async def manage_delete(
    request: Request,
    background_tasks: BackgroundTasks,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf_multipart(request, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"]
        res = await delete_video_by_owner(conn, video_id, user["user_uid"])
        ok = res.endswith("1")
        if not ok:
            raise HTTPException(status_code=404, detail="Video not found")
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    asyncio.create_task(
        _bg_cleanup_after_delete(
            storage_client,
            rel_storage,
            video_id,
        )
    )
    return RedirectResponse("/manage", status_code=302)


# ---------- Upload ----------

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        cats = await list_categories(conn)
    finally:
        await release_conn(conn)

    csrf_token = _csrf_cookie(request)

    return templates.TemplateResponse(
        "manage/upload.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "current_user": user,
            "categories": cats,
            "csrf_token": csrf_token,
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
            # stage-0 placeholder (empty)
            "suggested_variants": [],
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
    status: str = Form("private"),
    category_id: Optional[str] = Form(None),
    permit_download: bool = Form(False),
    is_age_restricted: bool = Form(False),
    is_made_for_kids: bool = Form(False),
    generate_captions_flag: Optional[int] = Form(0, alias="generate_captions"),
    captions_lang: str = Form("auto"),
    ytconvert_variants: Optional[List[str]] = Form(None),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    import tempfile
    import shutil

    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf_multipart(request, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)

    if status not in ("public", "private", "unlisted"):
        raise HTTPException(status_code=400, detail="Invalid status")

    title_final = (title or "").strip() or _fallback_title(file)
    cat_id: Optional[str] = (category_id or "").strip() or None

    conn = await get_conn()
    try:
        cats = await list_categories(conn)
        if cat_id is not None and not await category_exists(conn, cat_id):
            form_data: Dict[str, Any] = {
                "title": title_final,
                "description": description,
                "status": status,
                "category_id": cat_id,
                "permit_download": bool(permit_download),
                "is_age_restricted": is_age_restricted,
                "is_made_for_kids": is_made_for_kids,
            }
            return templates.TemplateResponse(
                "manage/upload.html",
                {
                    "brand_logo_url": settings.BRAND_LOGO_URL,
                    "brand_tagline": settings.BRAND_TAGLINE,
                    "favicon_url": settings.FAVICON_URL,
                    "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                    "request": request,
                    "current_user": user,
                    "categories": cats,
                    "error": "Selected category does not exist.",
                    "form": form_data,
                    "csrf_token": _csrf_cookie(request),
                    "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
                    "suggested_variants": [],
                },
                status_code=400,
                headers={"Cache-Control": "no-store"},
            )

        video_id = gen_id(12)

        # --- ytconvert job request ---
        requested_variants: List[str] = []
        if ytconvert_variants:
            try:
                requested_variants = [str(x).strip() for x in ytconvert_variants if str(x).strip()]
            except Exception:
                requested_variants = []
        if requested_variants:
            requested_variants = expand_requested_variant_ids(requested_variants)
        if requested_variants:
            print(f"[UPLOAD] ytconvert requested_variants={requested_variants} video_id={video_id}")
        # --- /ytconvert job request ---

        storage_client: StorageClient = request.app.state.storage
        storage_rel = build_video_storage_rel(video_id)

        mkdirs_res = storage_client.mkdirs(storage_rel, exist_ok=True)
        if inspect.isawaitable(mkdirs_res):
            await mkdirs_res

        original_name = "original.webm"
        original_rel_path = storage_client.join(storage_rel, original_name)

        writer_ctx = storage_client.open_writer(original_rel_path, overwrite=True)
        if inspect.isawaitable(writer_ctx):
            writer_ctx = await writer_ctx

        if hasattr(writer_ctx, "__aenter__"):
            async with writer_ctx as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    wr = out.write(chunk)
                    if inspect.isawaitable(wr):
                        await wr
        else:
            with writer_ctx as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)

        meta_rel_path = storage_client.join(storage_rel, "meta.json")

        exists_res = storage_client.exists(meta_rel_path)
        if inspect.isawaitable(exists_res):
            meta_exists = bool(await exists_res)
        else:
            meta_exists = bool(exists_res)

        if not meta_exists:
            writer_ctx2 = storage_client.open_writer(meta_rel_path, overwrite=True)
            if inspect.isawaitable(writer_ctx2):
                writer_ctx2 = await writer_ctx2

            payload = b'{"processing":"uploaded"}'
            if hasattr(writer_ctx2, "__aenter__"):
                async with writer_ctx2 as f:
                    wr = f.write(payload)
                    if inspect.isawaitable(wr):
                        await wr
            else:
                with writer_ctx2 as f:
                    f.write(payload)

        # DB record uses relative storage path!!
        await create_video(
            conn=conn,
            video_id=video_id,
            author_uid=user["user_uid"],
            title=title_final,
            description=description,
            status=status,
            storage_path=storage_rel,
            category_id=cat_id,
            permit_download=bool(permit_download),
            is_age_restricted=is_age_restricted,
            is_made_for_kids=is_made_for_kids,
        )

        local_job_id = None
        if requested_variants:
            try:
                local_job_id = await create_ytconvert_job(
                    conn=conn,
                    video_id=video_id,
                    author_uid=user["user_uid"],
                    requested_variants=requested_variants,
                )
            except Exception as e:
                print(f"[YTCONVERT] integration error local_job_id={local_job_id} exc={e!r}")

        storage_abs_root = storage_client.to_abs("")
        original_abs_path_storage = storage_client.to_abs(original_rel_path)

        is_local_mode = os.path.exists(original_abs_path_storage)

        tmp_dir = None
        original_abs_path = original_abs_path_storage

        if not is_local_mode:
            tmp_dir = tempfile.mkdtemp(prefix="yt_up_")
            original_abs_path = os.path.join(tmp_dir, original_name)

            reader_ctx = storage_client.open_reader(original_rel_path)
            if inspect.isawaitable(reader_ctx):
                reader_ctx = await reader_ctx

            if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
                async for chunk in reader_ctx:
                    if chunk:
                        with open(original_abs_path, "ab") as lf:
                            lf.write(chunk)
            else:
                for chunk in reader_ctx:
                    if chunk:
                        with open(original_abs_path, "ab") as lf:
                            lf.write(chunk)

        duration = await async_probe_duration_seconds(original_abs_path)

        src_info = await _probe_basic_video_info_ffprobe(original_abs_path)
        src_info["duration_sec"] = duration
        suggested_variants = compute_suggested_variants(
            src_info,
            prefer_container="mp4",
            include_audio=True,
        )

        offsets = pick_thumbnail_offsets(duration)

        if is_local_mode:
            thumbs_rel_dir = storage_client.join(storage_rel, "thumbs")
            thumbs_abs_dir = storage_client.to_abs(thumbs_rel_dir)
        else:
            thumbs_rel_dir = storage_client.join(storage_rel, "thumbs")
            thumbs_abs_dir = os.path.join(tmp_dir or tempfile.gettempdir(), "thumbs")
        os.makedirs(thumbs_abs_dir, exist_ok=True)

        candidates_abs: List[str] = []
        try:
            candidates_abs = await async_generate_thumbnails(original_abs_path, thumbs_abs_dir, offsets)
        except Exception as e:
            print(f"[UPLOAD] thumbnails generation failed video_id={video_id}: {e}")
            candidates_abs = []

        candidates: List[Dict[str, str]] = []
        selected_rel: Optional[str] = None

        if is_local_mode:
            selected_abs: Optional[str] = candidates_abs[0] if candidates_abs else None
            selected_rel = (os.path.relpath(selected_abs, storage_abs_root) if selected_abs else None)
            if selected_rel:
                await upsert_video_asset(conn, video_id, "thumbnail_default", selected_rel)
            for p_abs in candidates_abs:
                rel = os.path.relpath(p_abs, storage_abs_root)
                candidates.append({"rel": rel, "url": build_storage_url(rel), "sel": "1" if selected_rel == rel else "0"})
        else:
            mkdirs_res2 = storage_client.mkdirs(thumbs_rel_dir, exist_ok=True)
            if inspect.isawaitable(mkdirs_res2):
                await mkdirs_res2

            uploaded_rels: List[str] = []
            for p_abs in candidates_abs:
                fname = os.path.basename(p_abs)
                remote_rel = storage_client.join(thumbs_rel_dir, fname)
                writer_ctx3 = storage_client.open_writer(remote_rel, overwrite=True)
                if inspect.isawaitable(writer_ctx3):
                    writer_ctx3 = await writer_ctx3
                if hasattr(writer_ctx3, "__aenter__"):
                    async with writer_ctx3 as f:
                        with open(p_abs, "rb") as lf:
                            while True:
                                chunk = lf.read(1024 * 1024)
                                if not chunk:
                                    break
                                wr = f.write(chunk)
                                if inspect.isawaitable(wr):
                                    await wr
                else:
                    with writer_ctx3 as f:
                        with open(p_abs, "rb") as lf:
                            while True:
                                chunk = lf.read(1024 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                uploaded_rels.append(remote_rel)

            selected_rel = uploaded_rels[0] if uploaded_rels else None
            if selected_rel:
                await upsert_video_asset(conn, video_id, "thumbnail_default", selected_rel)
            for remote_rel in uploaded_rels:
                candidates.append({"rel": remote_rel, "url": build_storage_url(remote_rel), "sel": "1" if selected_rel == remote_rel else "0"})

        anim_abs_local = os.path.join(thumbs_abs_dir, "thumb_anim.webp")
        start_sec = offsets[0] if offsets else 1
        ok_anim = await async_generate_animated_preview(
            original_abs_path, anim_abs_local, start_sec=start_sec, duration_sec=3, fps=12
        )

        if ok_anim and os.path.exists(anim_abs_local):
            if is_local_mode:
                anim_rel = os.path.relpath(anim_abs_local, storage_abs_root)
                await upsert_video_asset(conn, video_id, "thumbnail_anim", anim_rel)
            else:
                anim_rel_remote = storage_client.join(thumbs_rel_dir, "thumb_anim.webp")
                writer_ctx_anim = storage_client.open_writer(anim_rel_remote, overwrite=True)
                if inspect.isawaitable(writer_ctx_anim):
                    writer_ctx_anim = await writer_ctx_anim
                if hasattr(writer_ctx_anim, "__aenter__"):
                    async with writer_ctx_anim as f:
                        with open(anim_abs_local, "rb") as lf:
                            while True:
                                chunk = lf.read(1024 * 1024)
                                if not chunk:
                                    break
                                wr = f.write(chunk)
                                if inspect.isawaitable(wr):
                                    await wr
                else:
                    with writer_ctx_anim as f:
                        with open(anim_abs_local, "rb") as lf:
                            while True:
                                chunk = lf.read(1024 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                await upsert_video_asset(conn, video_id, "thumbnail_anim", anim_rel_remote)

        await set_video_ready(conn, video_id, duration)

        if local_job_id and requested_variants:
            try:
                schedule_ytconvert_job(
                    request=request,
                    local_job_id=local_job_id,
                    video_id=video_id,
                    storage_rel=storage_rel,
                    original_rel_path=original_rel_path,
                    requested_variant_ids=requested_variants,
                )
            except Exception as e:
                print(f"[UPLOAD] ytconvert scheduling failed video_id={video_id}: {e}")

        want_caps = bool(generate_captions_flag)
        lang_req = (captions_lang or "auto").strip().lower()
        if want_caps:
            try:
                async def _caption_worker():
                    import tempfile as _tf
                    import shutil as _sh

                    tmp_local_dir = None
                    src_for_caps = original_abs_path
                    if not is_local_mode:
                        tmp_local_dir = _tf.mkdtemp(prefix="ytcaps_")
                        src_for_caps = os.path.join(tmp_local_dir, original_name)
                        reader_ctx_local = storage_client.open_reader(original_rel_path)
                        if inspect.isawaitable(reader_ctx_local):
                            reader_ctx_local = await reader_ctx_local
                        if hasattr(reader_ctx_local, "__aiter__") or hasattr(reader_ctx_local, "__anext__"):
                            async for _chunk in reader_ctx_local:
                                if _chunk:
                                    with open(src_for_caps, "ab") as _lf:
                                        _lf.write(_chunk)
                        else:
                            for _chunk in reader_ctx_local:
                                if _chunk:
                                    with open(src_for_caps, "ab") as _lf:
                                        _lf.write(_chunk)
                    try:
                        rel_vtt, meta = await generate_captions(
                            video_id=video_id,
                            storage_rel=storage_rel,
                            src_path=src_for_caps,
                            lang=lang_req or "auto",
                            storage_client=storage_client,
                        )
                        conn2 = await get_conn()
                        try:
                            await set_video_captions(conn2, video_id, rel_vtt, meta.get("lang") or lang_req, meta)
                        finally:
                            await release_conn(conn2)
                        print(f"[UPLOAD] captions generated video_id={video_id} lang={meta.get('lang')}")
                    except Exception as e:
                        print(f"[UPLOAD] captions generation failed video_id={video_id}: {e}")
                    finally:
                        if tmp_local_dir and os.path.isdir(tmp_local_dir):
                            try:
                                _sh.rmtree(tmp_local_dir)
                            except Exception:
                                pass

                asyncio.create_task(_caption_worker())
            except Exception as e:
                print(f"[UPLOAD] captions background scheduling failed video_id={video_id}: {e}")
        else:
            print(f"[UPLOAD] captions generation skipped video_id={video_id}")

        try:
            min_dur = getattr(settings, "AUTO_SPRITES_MIN_DURATION", 3)
            auto_enabled = getattr(settings, "AUTO_SPRITES_ENABLED", True)
            if auto_enabled and (isinstance(duration, (int, float)) and duration >= min_dur):
                storage_rel_db = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
                if storage_rel_db:
                    original_abs_for_job = storage_client.to_abs(storage_client.join(storage_rel_db, "original.webm"))
                    out_base_abs = storage_client.to_abs(storage_rel_db)
                    if os.path.exists(original_abs_for_job):
                        job = await create_thumbnails_job(
                            video_id=video_id,
                            src_path=original_abs_for_job,
                            out_base_path=out_base_abs,
                            extra=None,
                        )
                        print(f"[AUTOSPRITES] queued video_id={video_id} job={job.get('job_id')}")
                    else:
                        print(f"[AUTOSPRITES] original missing for video_id={video_id}")
                else:
                    print(f"[AUTOSPRITES] storage path not found for video_id={video_id}")
            else:
                print(f"[AUTOSPRITES] skip video_id={video_id} enabled={auto_enabled} duration={duration}")
        except Exception as e:
            print(f"[AUTOSPRITES] failed to enqueue video_id={video_id}: {e}")

        if not is_local_mode and tmp_dir and os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass

    finally:
        await release_conn(conn)

    try:
        fire_and_forget_reindex(video_id)
    except Exception:
        pass

    cookie_tok = _csrf_cookie(request)
    context_token = cookie_tok
    resp = templates.TemplateResponse(
        "manage/select_thumbnail.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "current_user": user,
            "video_id": video_id,
            "candidates": candidates,
            "csrf_token": context_token,
            "suggested_variants": suggested_variants,
            "source_info": src_info,
            "_csrf_debug": f"<!-- CSRF cookie={cookie_tok} form={context_token} -->",
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
        },
        headers={"Cache-Control": "no-store"},
    )
    return resp


@router.post("/upload/select-thumbnail")
@router.post("/upload/select-thumbnail/")
@router.post("/upload/select_thumbnail")
@router.post("/upload/select_thumbnail/")
async def select_thumbnail(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    ctype = (request.headers.get("content-type") or "").lower()
    form_csrf = ""
    form_video_id: Optional[str] = None
    form_selected_rel: Optional[str] = None

    raw_len = 0
    try:
        raw = await request.body()
        raw_len = len(raw or b"")
    except Exception:
        raw = b""

    if "application/x-www-form-urlencoded" in ctype:
        try:
            from urllib.parse import parse_qs
            parsed = parse_qs(raw.decode("utf-8", "ignore"), keep_blank_values=True)
            form_csrf = (parsed.get("csrf_token", [""])[0] or "").strip()
            form_video_id = (parsed.get("video_id", [""])[0] or "").strip() or None
            form_selected_rel = (parsed.get("selected_rel", [""])[0] or "").strip() or None
        except Exception:
            form_csrf = ""
            form_video_id = None
            form_selected_rel = None
    elif "multipart/form-data" in ctype:
        try:
            data = await request.form()
            form_csrf = (data.get("csrf_token") or "").strip()
            form_video_id = (data.get("video_id") or "").strip() or None
            form_selected_rel = (data.get("selected_rel") or "").strip() or None
        except Exception:
            pass

    qp = request.query_params
    if not form_video_id:
        qv = qp.get("video_id")
        if qv:
            form_video_id = qv.strip() or None
    if not form_selected_rel:
        qsr = qp.get("selected_rel")
        if qsr:
            form_selected_rel = qsr.strip() or None
    if not form_csrf:
        qct = qp.get("csrf_token")
        if qct:
            form_csrf = qct.strip()

    print(f"[THUMB POST] ctype={ctype} raw_len={raw_len} cookie={_csrf_cookie(request)!r} form_csrf={form_csrf!r} video_id={form_video_id!r} selected_rel={form_selected_rel!r}")

    if not _validate_csrf_multipart(request, form_csrf):
        return JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)

    if not form_video_id or not form_selected_rel:
        return JSONResponse({"ok": False, "error": "missing_fields"}, status_code=400)

    sel = form_selected_rel
    if sel.startswith("http://") or sel.startswith("https://"):
        idx = sel.find("/storage/")
        if idx >= 0:
            sel = sel[idx + len("/storage/") :]
    sel = sel.replace("\\", "/").lstrip("/")

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, form_video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"].rstrip("/") + "/"
        expected_prefix = rel_storage + "thumbs/"

        if not sel.startswith(expected_prefix):
            raise HTTPException(status_code=400, detail="Invalid thumbnail path")

        storage_client: StorageClient = request.app.state.storage
        ex = storage_client.exists(sel)
        if inspect.isawaitable(ex):
            ex = await ex
        if not ex:
            raise HTTPException(status_code=400, detail="Thumbnail not found on disk")

        await upsert_video_asset(conn, form_video_id, "thumbnail_default", sel)
    finally:
        await release_conn(conn)

    return RedirectResponse(f"/manage/edit?v={form_video_id}", status_code=302)