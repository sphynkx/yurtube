from typing import Any
from urllib.parse import quote_plus

import asyncpg
from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.users_db import authenticate_user, create_user, get_user_by_username, get_user_by_email
from utils.idgen_ut import gen_id
from utils.security_ut import (
    clear_session_cookie,
    create_session_cookie,
    get_current_user,
    hash_password,
)
from config.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Any:
    if get_current_user(request):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("auth/login.html",
    {
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_tagline": settings.BRAND_TAGLINE,
        "favicon_url": settings.FAVICON_URL,
        "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        "request": request,
        "current_user": None
    })


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> Any:
    conn = await get_conn()
    try:
        user = await authenticate_user(conn, username, password)
    finally:
        await release_conn(conn)

    if not user:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "brand_logo_url": settings.BRAND_LOGO_URL,
                "brand_tagline": settings.BRAND_TAGLINE,
                "favicon_url": settings.FAVICON_URL,
                "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                "request": request,
                "current_user": None,
                "error": "Invalid username or password",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    create_session_cookie(redirect, user["user_uid"])
    # Provider marker
    redirect.set_cookie(
        "yt_authp", "local",
        httponly=True, secure=True, samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    local_name = user.get("username") or username
    redirect.set_cookie(
        "yt_lname", quote_plus(str(local_name), safe="()"),
        httponly=False, secure=True, samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return redirect


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> Any:
    if get_current_user(request):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("auth/register.html",
    {
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_tagline": settings.BRAND_TAGLINE,
        "favicon_url": settings.FAVICON_URL,
        "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        "request": request,
        "current_user": None
    })


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
) -> Any:
    conn = await get_conn()
    try:
        existing_user = await get_user_by_username(conn, username)
        if existing_user:
            return templates.TemplateResponse(
                "auth/register.html",
                {
                    "brand_logo_url": settings.BRAND_LOGO_URL,
                    "brand_tagline": settings.BRAND_TAGLINE,
                    "favicon_url": settings.FAVICON_URL,
                    "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                    "request": request,
                    "current_user": None,
                    "error": "Username already taken",
                    "form": {"username": username, "email": email},
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        existing_email = await get_user_by_email(conn, email)
        if existing_email:
            return templates.TemplateResponse(
                "auth/register.html",
                {
                    "brand_logo_url": settings.BRAND_LOGO_URL,
                    "brand_tagline": settings.BRAND_TAGLINE,
                    "favicon_url": settings.FAVICON_URL,
                    "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                    "request": request,
                    "current_user": None,
                    "error": "Email is already registered",
                    "form": {"username": username, "email": email},
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user_uid = gen_id(20)
        channel_id = gen_id(24)
        try:
            await create_user(
                conn=conn,
                user_uid=user_uid,
                channel_id=channel_id,
                username=username,
                email=email,
                password_hash=hash_password(password),
            )
        except asyncpg.UniqueViolationError:
            return templates.TemplateResponse(
                "auth/register.html",
                {
                    "brand_logo_url": settings.BRAND_LOGO_URL,
                    "brand_tagline": settings.BRAND_TAGLINE,
                    "favicon_url": settings.FAVICON_URL,
                    "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                    "request": request,
                    "current_user": None,
                    "error": "Username or email is already registered",
                    "form": {"username": username, "email": email},
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    finally:
        await release_conn(conn)

    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    create_session_cookie(redirect, user_uid)
    redirect.set_cookie(
        "yt_authp", "local",
        httponly=True, secure=True, samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    redirect.set_cookie(
        "yt_lname", quote_plus(str(username), safe="()"),
        httponly=False, secure=True, samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return redirect


@router.post("/logout")
async def logout_post() -> Any:
    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(redirect)
    redirect.delete_cookie("yt_authp")
    redirect.delete_cookie("yt_lname")
    return redirect


@router.get("/logout")
async def logout_get() -> Any:
    """
    Permit 405
    """
    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(redirect)
    redirect.delete_cookie("yt_authp")
    redirect.delete_cookie("yt_lname")
    return redirect