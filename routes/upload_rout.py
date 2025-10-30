import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.categories_db import category_exists, list_categories
from db.videos_db import create_video, list_my_videos, set_video_ready
from db.assets_db import upsert_video_asset
from services.ffmpeg_srv import generate_default_thumbnail, probe_duration_seconds
from utils.idgen_ut import gen_id
from utils.path_ut import build_video_storage_dir
from utils.security_ut import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/manage", response_class=HTMLResponse)
async def manage_home(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        my_videos = await list_my_videos(conn, user["user_uid"])
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "manage/my_videos.html",
        {"request": request, "current_user": user, "videos": my_videos},
    )


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
    title: str = Form(...),
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

    cat_id: Optional[str] = (category_id or "").strip() or None

    conn = await get_conn()
    try:
        cats = await list_categories(conn)
        if cat_id is not None and not await category_exists(conn, cat_id):
            form_data: Dict[str, Any] = {
                "title": title,
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
            title=title,
            description=description,
            status=status,
            storage_path=rel_storage,
            category_id=cat_id,
            is_age_restricted=is_age_restricted,
            is_made_for_kids=is_made_for_kids,
        )

        thumbs_dir = os.path.join(storage_dir, "thumbs")
        thumb_abs = generate_default_thumbnail(original_path, thumbs_dir)
        if thumb_abs:
            rel_thumb = os.path.relpath(thumb_abs, settings.STORAGE_ROOT)
            await upsert_video_asset(conn, video_id, "thumbnail_default", rel_thumb)

        duration = probe_duration_seconds(original_path)
        await set_video_ready(conn, video_id, duration)

    finally:
        await release_conn(conn)

    return RedirectResponse(f"/watch?v={video_id}", status_code=302)