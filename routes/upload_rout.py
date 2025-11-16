import os
import time
import shutil
import subprocess
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

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
from db.comments.root_db import delete_all_comments_for_video

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _csrf_cookie_name() -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")

def _csrf_from_cookie(request: Request) -> str:
    return (request.cookies.get(_csrf_cookie_name()) or "").strip()



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
        subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
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

    try:
        _bg_delete_index(video_id)
    except Exception:
        pass

    try:
        _bg_delete_comments(video_id, timeout_sec=5.0)
    except Exception:
        pass

# ---------------- Manage ----------------

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

    csrf_token = _csrf_from_cookie(request)

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

# ---------------- Upload + thumbnails flow ----------------

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

    csrf_token = _csrf_from_cookie(request)

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
                    "csrf_token": _csrf_from_cookie(request),
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

        # Animated preview: 3 seconds
        anim_abs = os.path.join(thumbs_dir, "thumb_anim.webp")
        start_sec = offsets[0] if offsets else 1
        ok_anim = await async_generate_animated_preview(
            original_path, anim_abs, start_sec=start_sec, duration_sec=3, fps=12
        )
        if ok_anim and os.path.exists(anim_abs):
            anim_rel = os.path.relpath(anim_abs, settings.STORAGE_ROOT)
            await upsert_video_asset(conn, video_id, "thumbnail_anim", anim_rel)

        await set_video_ready(conn, video_id, duration)

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

    return templates.TemplateResponse(
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
            "csrf_token": _csrf_from_cookie(request),
        },
        headers={"Cache-Control": "no-store"},
    )

@router.post("/upload/select-thumbnail")
@router.post("/upload/select-thumbnail/")
@router.post("/upload/select_thumbnail")
@router.post("/upload/select_thumbnail/")
async def select_thumbnail(
    request: Request,
    video_id: str = Form(...),
    selected_rel: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    sel = (selected_rel or "").strip()
    if sel.startswith("http://") or sel.startswith("https://"):
        idx = sel.find("/storage/")
        if idx >= 0:
            sel = sel[idx + len("/storage/") :]
    sel = sel.replace("\\", "/").lstrip("/")

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"].rstrip("/") + "/"
        expected_prefix = rel_storage + "thumbs/"

        if not sel.startswith(expected_prefix):
            raise HTTPException(status_code=400, detail="Invalid thumbnail path")

        abs_path = os.path.join(settings.STORAGE_ROOT, sel)
        if not os.path.isfile(abs_path):
            raise HTTPException(status_code=400, detail="Thumbnail not found on disk")

        await upsert_video_asset(conn, video_id, "thumbnail_default", sel)
    finally:
        await release_conn(conn)

    return RedirectResponse("/manage", status_code=302)