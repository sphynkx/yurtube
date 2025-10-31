import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
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
    generate_thumbnails,
    pick_thumbnail_offsets,
    probe_duration_seconds,
)
from utils.idgen_ut import gen_id
from utils.path_ut import build_video_storage_dir, safe_remove_storage_relpath
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _fallback_title(file: UploadFile) -> str:
    base = (file.filename or "").strip()
    if base:
        name, _ = os.path.splitext(base)
        if name.strip():
            return name.strip()[:200]
    return "Video " + datetime.utcnow().strftime("%Y-%m-%d %H:%M")


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

    return templates.TemplateResponse(
        "manage/my_videos.html",
        {"request": request, "current_user": user, "videos": videos, "subscribers_count": subs_count},
    )


@router.post("/manage/delete")
async def manage_delete(request: Request, video_id: str = Form(...)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"]

        deleted = await delete_video(conn, video_id, user["user_uid"])
        if not deleted:
            raise HTTPException(status_code=404, detail="Video not found")
    finally:
        await release_conn(conn)

    safe_remove_storage_relpath(settings.STORAGE_ROOT, rel_storage)

    return RedirectResponse("/manage", status_code=302)


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

    return templates.TemplateResponse(
        "manage/upload.html",
        {"request": request, "current_user": user, "categories": cats},
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
                    "request": request,
                    "current_user": user,
                    "categories": cats,
                    "error": "Selected category does not exist.",
                    "form": form_data,
                },
                status_code=400,
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

        duration = probe_duration_seconds(original_path)
        offsets = pick_thumbnail_offsets(duration)
        thumbs_dir = os.path.join(storage_dir, "thumbs")
        candidates_abs = generate_thumbnails(original_path, thumbs_dir, offsets)

        selected_abs: Optional[str] = candidates_abs[0] if candidates_abs else None
        selected_rel: Optional[str] = (
            os.path.relpath(selected_abs, settings.STORAGE_ROOT) if selected_abs else None
        )
        if selected_rel:
            await upsert_video_asset(conn, video_id, "thumbnail_default", selected_rel)

        await set_video_ready(conn, video_id, duration)

        candidates: List[Dict[str, str]] = []
        for p_abs in candidates_abs:
            rel = os.path.relpath(p_abs, settings.STORAGE_ROOT)
            candidates.append(
                {"rel": rel, "url": build_storage_url(rel), "sel": "1" if selected_rel == rel else "0"}
            )
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "manage/select_thumbnail.html",
        {
            "request": request,
            "current_user": user,
            "video_id": video_id,
            "candidates": candidates,
        },
    )


@router.post("/upload/select-thumbnail")
async def select_thumbnail(
    request: Request,
    video_id: str = Form(...),
    selected_rel: str = Form(...),
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
        expected_prefix = rel_storage.rstrip("/") + "/thumbs/"

        sel_norm = selected_rel.replace("\\", "/").lstrip("/")
        if not sel_norm.startswith(expected_prefix):
            raise HTTPException(status_code=400, detail="Invalid thumbnail path")

        abs_path = os.path.join(settings.STORAGE_ROOT, sel_norm)
        if not os.path.isfile(abs_path):
            raise HTTPException(status_code=400, detail="Thumbnail not found on disk")

        await upsert_video_asset(conn, video_id, "thumbnail_default", sel_norm)
    finally:
        await release_conn(conn)

    return RedirectResponse("/manage", status_code=302)