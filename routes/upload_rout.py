import os
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
)

from services.ytms_client_srv import create_thumbnails_job
from db.ytms_db import fetch_video_storage_path
 
from services.ffmpeg_srv import (
    async_generate_thumbnails,
    pick_thumbnail_offsets,
    async_probe_duration_seconds,
    async_generate_animated_preview,
)
from services.search.indexer_srch import fire_and_forget_reindex, delete_from_index
from utils.idgen_ut import gen_id
from utils.path_ut import build_video_storage_dir
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from db.comments.root_db import delete_all_comments_for_video  # best-effort

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

def _bg_delete_index(video_id: str) -> None:
    try:
        asyncio.run(delete_from_index(video_id))
    except Exception:
        pass

def _bg_delete_comments(video_id: str, timeout_sec: float = 5.0) -> None:
    try:
        async def _runner():
            await asyncio.wait_for(delete_all_comments_for_video(video_id), timeout=timeout_sec)
        asyncio.run(_runner())
    except Exception:
        pass

def _bg_cleanup_after_delete_sync(storage_root: str, storage_rel: str, video_id: str) -> None:
    try:
        storage_abs = os.path.join(storage_root, storage_rel)
        deleting_path = storage_abs
        if os.path.exists(storage_abs):
            ts = int(time.time())
            cand = storage_abs + f".deleting.{ts}"
            try:
                os.rename(storage_abs, cand)
                deleting_path = cand
            except Exception:
                deleting_path = storage_abs
            _bg_rm_rf(deleting_path)
    except Exception:
        pass
    _bg_delete_index(video_id)
    _bg_delete_comments(video_id, timeout_sec=5.0)

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

        res = await conn.execute(
            "DELETE FROM videos WHERE video_id = $1 AND author_uid = $2",
            video_id,
            user["user_uid"],
        )
        ok = res.endswith("1")
        if not ok:
            raise HTTPException(status_code=404, detail="Video not found")
    finally:
        await release_conn(conn)

    background_tasks.add_task(
        _bg_cleanup_after_delete_sync,
        getattr(settings, "STORAGE_ROOT", "/var/www/storage"),
        rel_storage,
        video_id,
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
    is_age_restricted: bool = Form(False),
    is_made_for_kids: bool = Form(False),
    csrf_token: Optional[str] = Form(None),
) -> Any:
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
                },
                status_code=400,
                headers={"Cache-Control": "no-store"},
            )

        video_id = gen_id(12)
        storage_dir = build_video_storage_dir(settings.STORAGE_ROOT, video_id)
        os.makedirs(storage_dir, exist_ok=True)

        original_name = "original.webm"
        original_path = os.path.join(storage_dir, original_name)

        with open(original_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        meta_path = os.path.join(storage_dir, "meta.json")
        if not os.path.exists(meta_path):
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write('{"processing":"uploaded"}')

        rel_storage = os.path.relpath(storage_dir, settings.STORAGE_ROOT)

        await create_video(
            conn=conn,
            video_id=video_id,
            author_uid=user["user_uid"],
            title=title_final,
            description=description,
            status=status,
            storage_path=rel_storage,
            category_id=cat_id,
            is_age_restricted=is_age_restricted,
            is_made_for_kids=is_made_for_kids,
        )

        duration = await async_probe_duration_seconds(original_path)
        offsets = pick_thumbnail_offsets(duration)
        thumbs_dir = os.path.join(storage_dir, "thumbs")
        candidates_abs = await async_generate_thumbnails(original_path, thumbs_dir, offsets)

        selected_abs: Optional[str] = candidates_abs[0] if candidates_abs else None
        selected_rel: Optional[str] = (
            os.path.relpath(selected_abs, settings.STORAGE_ROOT) if selected_abs else None
        )
        if selected_rel:
            await upsert_video_asset(conn, video_id, "thumbnail_default", selected_rel)

        anim_abs = os.path.join(thumbs_dir, "thumb_anim.webp")
        start_sec = offsets[0] if offsets else 1
        ok_anim = await async_generate_animated_preview(
            original_path, anim_abs, start_sec=start_sec, duration_sec=3, fps=12
        )
        if ok_anim and os.path.exists(anim_abs):
            anim_rel = os.path.relpath(anim_abs, settings.STORAGE_ROOT)
            await upsert_video_asset(conn, video_id, "thumbnail_anim", anim_rel)

        await set_video_ready(conn, video_id, duration)

        try:
            min_dur = getattr(settings, "AUTO_SPRITES_MIN_DURATION", 3)
            auto_enabled = getattr(settings, "AUTO_SPRITES_ENABLED", True)
            if auto_enabled and (isinstance(duration, (int, float)) and duration >= min_dur):
                storage_rel = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
                if storage_rel:
                    abs_root = getattr(settings, "STORAGE_ROOT", "/var/www/storage")
                    original_abs = os.path.join(abs_root, storage_rel, "original.webm")
                    if os.path.exists(original_abs):
                        job = await create_thumbnails_job(
                            video_id=video_id,
                            src_path=original_abs,
                            out_base_path=os.path.join(abs_root, storage_rel),
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

        candidates: List[Dict[str, str]] = []
        for p_abs in candidates_abs:
            rel = os.path.relpath(p_abs, settings.STORAGE_ROOT)
            candidates.append(
                {"rel": rel, "url": build_storage_url(rel), "sel": "1" if selected_rel == rel else "0"}
            )
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
            # mark tonen for debug (2DEL):
            "_csrf_debug": f"<!-- CSRF cookie={cookie_tok} form={context_token} -->",
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
        # w/o starlette
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

    # Fallback from query (temp)
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

    # DEBUG
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

        abs_path = os.path.join(settings.STORAGE_ROOT, sel)
        if not os.path.isfile(abs_path):
            raise HTTPException(status_code=400, detail="Thumbnail not found on disk")

        await upsert_video_asset(conn, form_video_id, "thumbnail_default", sel)
    finally:
        await release_conn(conn)

    return RedirectResponse("/manage", status_code=302)