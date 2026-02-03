import os
import time
import tempfile
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from services.ffmpeg_srv import generate_image_thumbnail
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

from db.account_profile_db import (
    fetch_profile_data,
    save_user_avatar_path,
    remove_user_avatar_record,
    unlink_google_identity_if_possible,
)

from services.ytstorage.base_srv import StorageClient

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _cache_bust(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if not url.startswith("/"):
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}cb={int(time.time())}"


async def _write_uploadfile_to_path(upload: UploadFile, dst_abs: str) -> None:
    with open(dst_abs, "wb") as f:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


async def _upload_local_file_to_storage(storage: StorageClient, rel_path: str, src_abs: str, overwrite: bool = True) -> None:
    writer_ctx = await storage.open_writer(rel_path, overwrite=overwrite)
    async with writer_ctx as w:
        with open(src_abs, "rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b:
                    break
                await w.write(b)


@router.get("/account", response_class=HTMLResponse)
async def account_home(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    data = await fetch_profile_data(user["user_uid"])
    profile_username = data["username"] or user.get("username") or ""
    avatar_rel = data["avatar_rel"]
    avatar_url = build_storage_url(avatar_rel) if avatar_rel else None
    sso_list = data["sso_list"]

    provider = request.cookies.get("yt_authp") or "local"

    sso_picture = None
    sso_name = None
    for ident in sso_list:
        if not sso_picture and ident.get("picture_url"):
            sso_picture = ident.get("picture_url")
        if not sso_name and (ident.get("display_name") or ident.get("email")):
            sso_name = ident.get("display_name") or ident.get("email")

    cookie_pic = request.cookies.get("yt_gpic")
    if not sso_picture and cookie_pic:
        sso_picture = cookie_pic

    if provider != "local":
        nav_avatar_url = sso_picture or avatar_url
        nav_display_name = sso_name or profile_username
        avatar_block_url = sso_picture or avatar_url
        show_sso_section = True
    else:
        nav_avatar_url = avatar_url or sso_picture
        nav_display_name = profile_username or sso_name or ""
        avatar_block_url = avatar_url or sso_picture
        show_sso_section = len(sso_list) > 0

    nav_avatar_url = _cache_bust(nav_avatar_url)
    avatar_block_url = _cache_bust(avatar_block_url)

    return templates.TemplateResponse(
        "account/profile.html",
        {
            "request": request,
            "current_user": {"user_uid": user["user_uid"], "username": profile_username},
            "avatar_url": avatar_block_url,
            "sso_identities": sso_list if show_sso_section else [],
            "google_picture": None,
            "nav_avatar_url": nav_avatar_url,
            "nav_display_name": nav_display_name,
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "storage_public_base_url": getattr(settings, "YTSTORAGE_PUBLIC_BASE_URL", None),
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

    storage: StorageClient = request.app.state.storage

    prefix = (user["user_uid"] or "")[:2]
    user_dir_rel = f"{prefix}/{user['user_uid']}".strip("/")

    # canonical rel paths in ytstorage
    original_rel = storage.join(user_dir_rel, "avatar.png")
    small_rel = storage.join(user_dir_rel, "avatar_small.png")

    # generate thumbnails locally in temp dir, then upload to ytstorage
    with tempfile.TemporaryDirectory(prefix="yurtube-avatar-") as tmpd:
        original_abs = os.path.join(tmpd, "avatar.png")
        small_abs = os.path.join(tmpd, "avatar_small.png")

        await _write_uploadfile_to_path(avatar, original_abs)

        # normalize/resize
        generate_image_thumbnail(original_abs, original_abs, 512)
        generate_image_thumbnail(original_abs, small_abs, 96)

        # ensure remote dir exists
        await storage.mkdirs(user_dir_rel, exist_ok=True)

        await _upload_local_file_to_storage(storage, original_rel, original_abs, overwrite=True)
        await _upload_local_file_to_storage(storage, small_rel, small_abs, overwrite=True)

    # store original path in DB (you can also store small if needed later)
    await save_user_avatar_path(user["user_uid"], original_rel)

    return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)


@router.post("/account/avatar/delete")
async def account_avatar_delete(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    await remove_user_avatar_record(user["user_uid"])

    storage: StorageClient = request.app.state.storage
    prefix = (user["user_uid"] or "")[:2]
    user_dir_rel = f"{prefix}/{user['user_uid']}".strip("/")

    # best-effort delete of files + directory (recursive supported by RemoteStorageClient.remove)
    try:
        await storage.remove(storage.join(user_dir_rel, "avatar.png"), recursive=False)  # type: ignore[arg-type]
    except Exception:
        pass
    try:
        await storage.remove(storage.join(user_dir_rel, "avatar_small.png"), recursive=False)  # type: ignore[arg-type]
    except Exception:
        pass
    try:
        await storage.remove(user_dir_rel, recursive=True)  # type: ignore[arg-type]
    except Exception:
        pass

    return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)


@router.post("/account/sso/google/unlink")
async def account_unlink_google(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    result = await unlink_google_identity_if_possible(user["user_uid"])
    if result == "no_google":
        return RedirectResponse("/account?msg=no_google", status_code=status.HTTP_302_FOUND)
    if result == "need_password_before_unlink":
        return RedirectResponse("/account?msg=need_password_before_unlink", status_code=status.HTTP_302_FOUND)

    resp = RedirectResponse("/account?msg=google_unlinked", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("yt_gname")
    resp.delete_cookie("yt_gpic")
    resp.set_cookie("yt_authp", "local", httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp