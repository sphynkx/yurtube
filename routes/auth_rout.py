from typing import Any, Optional
from urllib.parse import quote_plus
import secrets

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

# CSRF helpers
def _gen_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def _get_csrf_cookie(request: Request) -> str:
    name = getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")
    return (request.cookies.get(name) or "").strip()

def _same_origin(request: Request) -> bool:
    try:
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        host = request.headers.get("host") or ""
        from urllib.parse import urlparse
        u = urlparse(origin)
        return bool(u.netloc) and (u.netloc == host)
    except Exception:
        return False

def _validate_csrf(request: Request, form_token: Optional[str]) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    form_tok = (form_token or "").strip() or header_tok or qs_tok
    if cookie_tok and form_tok:
        try:
            import secrets as _sec
            return _sec.compare_digest(cookie_tok, form_tok)
        except Exception:
            return False
    # soft fallback for same-origin (useful for logout if token missing)
    if _same_origin(request) and (form_token or header_tok or qs_tok):
        return True
    return False

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Any:
    if get_current_user(request):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()
    resp = templates.TemplateResponse("auth/login.html",
    {
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_tagline": settings.BRAND_TAGLINE,
        "favicon_url": settings.FAVICON_URL,
        "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        "request": request,
        "current_user": None
    })
    if not _get_csrf_cookie(request):
        resp.set_cookie(getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"), csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return resp

@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)

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
    csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()
    resp = templates.TemplateResponse("auth/register.html",
    {
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_tagline": settings.BRAND_TAGLINE,
        "favicon_url": settings.FAVICON_URL,
        "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        "request": request,
        "current_user": None
    })
    if not _get_csrf_cookie(request):
        resp.set_cookie(getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"), csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return resp

@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)

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
async def logout_post(request: Request, csrf_token: Optional[str] = Form(None)) -> Any:
    if not _validate_csrf(request, csrf_token):
        return HTMLResponse('{"ok":false,"error":"csrf_required"}', status_code=403, media_type="application/json")
    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(redirect)
    redirect.delete_cookie("yt_authp")
    redirect.delete_cookie("yt_lname")
    return redirect

@router.get("/logout")
async def logout_get() -> Any:
    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(redirect)
    redirect.delete_cookie("yt_authp")
    redirect.delete_cookie("yt_lname")
    return redirect