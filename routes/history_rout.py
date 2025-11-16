import secrets
from typing import Any, List

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import list_history_distinct_latest
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# CSRF helpers
def _gen_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def _get_csrf_cookie(request: Request) -> str:
    return (request.cookies.get(settings.CSRF_COOKIE_NAME) or "").strip()

def _validate_csrf(request: Request, form_token: str | None) -> bool:
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
    return False

@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()
        resp = templates.TemplateResponse(
            "history.html",
            {
                "request": request,
                "current_user": None,
                "need_login": True,
                "videos": [],
                "csrf_token": csrf_token,
                "brand_logo_url": settings.BRAND_LOGO_URL,
                "brand_tagline": settings.BRAND_TAGLINE,
                "favicon_url": settings.FAVICON_URL,
                "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            },
        )
        if not _get_csrf_cookie(request):
            resp.set_cookie(settings.CSRF_COOKIE_NAME, csrf_token, httponly=False, secure=True, samesite="lax", path="/")
        return resp

    conn = await get_conn()
    try:
        rows = await list_history_distinct_latest(conn, user["user_uid"], limit=200, offset=0)
        videos: List[dict] = []
        for r in rows:
            d = dict(r)
            tap = d.get("thumb_asset_path")
            d["thumb_url"] = build_storage_url(tap) if tap else "/static/img/fallback_video_notfound.gif"
            d["author_avatar_url_small"] = f"/storage/users/{d['author_uid']}/avatar_small.png"
            videos.append(d)
    finally:
        await release_conn(conn)

    csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()
    resp = templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "current_user": user,
            "need_login": False,
            "videos": videos,
            "csrf_token": csrf_token,
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        },
    )
    if not _get_csrf_cookie(request):
        resp.set_cookie(settings.CSRF_COOKIE_NAME, csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return resp

# Inline history clear/remove (replace with DB helpers if they exist)

@router.post("/history/clear")
async def history_clear(
    request: Request,
    csrf_token: str = Form(None),
) -> Any:
    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM views WHERE user_uid = $1", user["user_uid"])
    finally:
        await release_conn(conn)
    return RedirectResponse("/history", status_code=302)

@router.post("/history/remove")
async def history_remove(
    request: Request,
    video_id: str = Form(...),
    csrf_token: str = Form(None),
) -> Any:
    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    conn = await get_conn()
    try:
        await conn.execute(
            "DELETE FROM views WHERE user_uid = $1 AND video_id = $2",
            user["user_uid"],
            video_id,
        )
    finally:
        await release_conn(conn)
    ref = request.headers.get("referer") or "/history"
    return RedirectResponse(ref, status_code=302)