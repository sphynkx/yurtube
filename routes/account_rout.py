import os
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.user_assets_db import delete_user_avatar, get_user_avatar_path, upsert_user_avatar
from services.ffmpeg_srv import generate_image_thumbnail
from utils.path_ut import build_user_storage_dir, safe_remove_storage_relpath
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/account", response_class=HTMLResponse)
async def account_home(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    conn = await get_conn()
    try:
        avatar_rel = await get_user_avatar_path(conn, user["user_uid"])
        avatar_url = build_storage_url(avatar_rel) if avatar_rel else None
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "account/profile.html",
        {
            "request": request,
            "current_user": user,
            "avatar_url": avatar_url,
        },
    )


@router.post("/account/profile", response_class=HTMLResponse)
async def account_profile_update(request: Request, avatar: Optional[UploadFile] = File(None)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    if avatar is None:
        return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)

    if not avatar.content_type or not avatar.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid avatar file")

    user_dir = build_user_storage_dir(settings.STORAGE_ROOT, user["user_uid"])
    os.makedirs(user_dir, exist_ok=True)

    original_abs = os.path.join(user_dir, "avatar.png")
    small_abs = os.path.join(user_dir, "avatar_small.png")

    with open(original_abs, "wb") as f:
        while True:
            chunk = await avatar.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    generate_image_thumbnail(original_abs, original_abs, 512)
    generate_image_thumbnail(original_abs, small_abs, 96)

    rel_path = os.path.relpath(original_abs, settings.STORAGE_ROOT)

    conn = await get_conn()
    try:
        await upsert_user_avatar(conn, user["user_uid"], rel_path)
    finally:
        await release_conn(conn)

    return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)


@router.post("/account/avatar/delete")
async def account_avatar_delete(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    # Remove DB link first
    conn = await get_conn()
    try:
        await delete_user_avatar(conn, user["user_uid"])
    finally:
        await release_conn(conn)

    # Remove storage/users/{uid} directory
    user_dir_abs = build_user_storage_dir(settings.STORAGE_ROOT, user["user_uid"])
    rel_user_dir = os.path.relpath(user_dir_abs, settings.STORAGE_ROOT)
    safe_remove_storage_relpath(settings.STORAGE_ROOT, rel_user_dir)

    return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)