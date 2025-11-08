import os
import time
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.user_assets_db import (
    delete_user_avatar,
    get_user_avatar_path,
    upsert_user_avatar,
)
from db.users_db import get_user_by_uid
from db.sso_db import list_identities_for_user
from services.ffmpeg_srv import generate_image_thumbnail
from utils.path_ut import build_user_storage_dir, safe_remove_storage_relpath
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _cache_bust(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}cb={int(time.time())}"


@router.get("/account", response_class=HTMLResponse)
async def account_home(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    conn = await get_conn()
    try:
        db_user = await get_user_by_uid(conn, user["user_uid"])
        profile_username = (db_user or {}).get("username") or user.get("username") or ""
        avatar_rel = await get_user_avatar_path(conn, user["user_uid"])
        avatar_url = build_storage_url(avatar_rel) if avatar_rel else None
        sso_list = await list_identities_for_user(conn, user["user_uid"])
    finally:
        await release_conn(conn)

    provider = request.cookies.get("yt_authp") or "local"

    google_picture = None
    google_name = None
    for ident in sso_list:
        if ident.get("provider") == "google":
            google_picture = ident.get("picture_url")
            google_name = ident.get("display_name") or ident.get("email")
            break

    if provider == "google":
        nav_avatar_url = google_picture or avatar_url
        nav_display_name = google_name or profile_username
        avatar_block_url = google_picture or avatar_url
        show_sso_section = True
    else:
        nav_avatar_url = avatar_url or google_picture
        nav_display_name = profile_username or google_name or ""
        avatar_block_url = avatar_url or google_picture
        show_sso_section = False

    nav_avatar_url = _cache_bust(nav_avatar_url)
    avatar_block_url = _cache_bust(avatar_block_url)

    return templates.TemplateResponse(
        "account/profile.html",
        {
            "request": request,
            "current_user": {"user_uid": user["user_uid"], "username": profile_username},
            "avatar_url": avatar_block_url,
            "sso_identities": sso_list if show_sso_section else [],
            "google_picture": google_picture,
            "nav_avatar_url": nav_avatar_url,
            "nav_display_name": nav_display_name,
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

    conn = await get_conn()
    try:
        await delete_user_avatar(conn, user["user_uid"])
    finally:
        await release_conn(conn)

    user_dir_abs = build_user_storage_dir(settings.STORAGE_ROOT, user["user_uid"])
    rel_user_dir = os.path.relpath(user_dir_abs, settings.STORAGE_ROOT)
    safe_remove_storage_relpath(settings.STORAGE_ROOT, rel_user_dir)

    return RedirectResponse("/account", status_code=status.HTTP_302_FOUND)

@router.post("/account/sso/google/unlink")
async def account_unlink_google(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    conn = await get_conn()
    try:
        ident = await conn.fetchrow(
            "SELECT subject FROM sso_identities WHERE provider='google' AND user_uid=$1 LIMIT 1",
            user["user_uid"],
        )
        if not ident:
            return RedirectResponse("/account?msg=no_google", status_code=status.HTTP_302_FOUND)
        row_pw = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE user_uid=$1",
            user["user_uid"],
        )
        pwd_hash = row_pw["password_hash"] if row_pw else ""
        if not pwd_hash:
            # If locall pass is absent - cannot unlink - else we cannot login
            return RedirectResponse("/account?msg=need_password_before_unlink", status_code=status.HTTP_302_FOUND)

        await conn.execute(
            "DELETE FROM sso_identities WHERE provider='google' AND user_uid=$1",
            user["user_uid"],
        )
    finally:
        await release_conn(conn)

    # Clean up Google-cookies
    resp = RedirectResponse("/account?msg=google_unlinked", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("yt_gname")
    resp.delete_cookie("yt_gpic")
    resp.set_cookie("yt_authp", "local", httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp
