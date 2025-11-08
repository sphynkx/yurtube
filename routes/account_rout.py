import os
import time
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from services.ffmpeg_srv import generate_image_thumbnail
from utils.path_ut import build_user_storage_dir, safe_remove_storage_relpath
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

from db.account_profile_db import (
    fetch_profile_data,
    save_user_avatar_path,
    remove_user_avatar_record,
    unlink_google_identity_if_possible,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _cache_bust(url: Optional[str]) -> Optional[str]:
    """
    Append a timestamp query param to force browsers to reload updated images.
    Only applied to local paths (starting with "/") to avoid breaking external CDN URLs.
    """
    if not url:
        return None
    if not url.startswith("/"):
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}cb={int(time.time())}"


@router.get("/account", response_class=HTMLResponse)
async def account_home(request: Request) -> Any:
    """
    Account profile page:
    - Requires authenticated user
    - Loads avatar asset path
    - Loads SSO identities (shown when present)
    - Prepares vars for header (avatar + display name)
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    data = await fetch_profile_data(user["user_uid"])
    profile_username = data["username"] or user.get("username") or ""
    avatar_rel = data["avatar_rel"]
    avatar_url = build_storage_url(avatar_rel) if avatar_rel else None
    sso_list = data["sso_list"]

    provider = request.cookies.get("yt_authp") or "local"

    # Find first available SSO picture/name (any provider)
    sso_picture = None
    sso_name = None
    for ident in sso_list:
        if not sso_picture and ident.get("picture_url"):
            sso_picture = ident.get("picture_url")
        if not sso_name and (ident.get("display_name") or ident.get("email")):
            sso_name = ident.get("display_name") or ident.get("email")

    # Cookie fallbacks (in case DB identity is not yet visible)
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
        },
    )


@router.post("/account/profile", response_class=HTMLResponse)
async def account_profile_update(request: Request, avatar: Optional[UploadFile] = File(None)) -> Any:
    """
    Update avatar:
    - Accepts an image file
    - Stores original + small thumbnail
    - Upserts DB record for avatar path
    """
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

    await save_user_avatar_path(user["user_uid"], rel_path)

    return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)


@router.post("/account/avatar/delete")
async def account_avatar_delete(request: Request) -> Any:
    """
    Delete current avatar:
    - Removes DB record
    - Deletes storage directory for the user
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    await remove_user_avatar_record(user["user_uid"])

    user_dir_abs = build_user_storage_dir(settings.STORAGE_ROOT, user["user_uid"])
    rel_user_dir = os.path.relpath(user_dir_abs, settings.STORAGE_ROOT)
    safe_remove_storage_relpath(settings.STORAGE_ROOT, rel_user_dir)

    return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)


@router.post("/account/sso/google/unlink")
async def account_unlink_google(request: Request) -> Any:
    """
    Unlink Google identity:
    - Requires existing Google SSO
    - Requires local password (prevents losing final login method)
    - Deletes identity and resets header cookies to local
    """
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