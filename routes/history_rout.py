## SRTG_DONE
## SRTG_2MODIFY: STORAGE_
## SRTG_2MODIFY: build_storage_url(
## SRTG_2MODIFY: os.path.
## SRTG_2MODIFY: abs_
## SRTG_2MODIFY: _path
import secrets
from typing import Any, List, Optional
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import list_history_distinct_latest
from db.history_db import clear_history, remove_history_item
from utils.url_ut import build_storage_url
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
from utils.format_ut import fmt_dt

# --- Storage abstraction ---
from services.storage.base_srv import StorageClient

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt

# --- CSRF helpers ---

def _gen_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def _get_csrf_cookie(request: Request) -> str:
    return (request.cookies.get(settings.CSRF_COOKIE_NAME) or "").strip()

def _is_https(request: Request) -> bool:
    xf_proto = (request.headers.get("x-forwarded-proto") or "").lower().strip()
    if xf_proto == "https":
        return True
    fwd = (request.headers.get("forwarded") or "").lower()
    if "proto=https" in fwd:
        return True
    return request.url.scheme == "https"

def _validate_csrf(request: Request, form_token: Optional[str]) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    form_tok = (form_token or "").strip() or header_tok
    ##print("[HISTORY CSRF]", "cookie=", cookie_tok, "form=", form_tok, "hdr=", header_tok)
    if not cookie_tok or not form_tok:
        return False
    try:
        import secrets as _sec
        return _sec.compare_digest(cookie_tok, form_tok)
    except Exception:
        return False

# --- Helpers ---

def _augment(vrow: dict, storage_client: StorageClient) -> dict:
    v = dict(vrow)
    tap = v.get("thumb_asset_path")
    v["thumb_url"] = build_storage_url(tap) if tap else DEFAULT_THUMB_DATA_URI
    if tap and "/" in tap:
        anim_rel = tap.rsplit("/", 1)[0] + "/thumb_anim.webp"
        v["thumb_anim_url"] = build_storage_url(anim_rel) if storage_client.exists(anim_rel) else None
    else:
        v["thumb_anim_url"] = None
    return v

# --- GET /history ---

@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request) -> Any:
    user = get_current_user(request)
    csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()
    ##print("[HISTORY GET] cookie=", _get_csrf_cookie(request), "ctx=", csrf_token)
    if not user:
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
                "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
            },
        )
        if not _get_csrf_cookie(request):
            resp.set_cookie(
                settings.CSRF_COOKIE_NAME,
                csrf_token,
                httponly=False,
                secure=_is_https(request),
                samesite="lax",
                path="/",
            )
        return resp

    conn = await get_conn()
    try:
        rows = await list_history_distinct_latest(conn, user["user_uid"], limit=200, offset=0)
        storage_client: StorageClient = request.app.state.storage
        videos: List[dict] = [_augment(dict(r), storage_client) for r in rows]
    finally:
        await release_conn(conn)

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
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
        },
    )
    if not _get_csrf_cookie(request):
        resp.set_cookie(
            settings.CSRF_COOKIE_NAME,
            csrf_token,
            httponly=False,
            secure=_is_https(request),
            samesite="lax",
            path="/",
        )
    return resp

# --- POST clear ---

@router.post("/history/clear")
async def history_clear(
    request: Request,
    csrf_token: Optional[str] = Form(None),
) -> Any:
    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    conn = await get_conn()
    try:
        await clear_history(conn, user["user_uid"])
    finally:
        await release_conn(conn)
    return RedirectResponse("/history", status_code=302)

# --- POST remove item ---

@router.post("/history/remove1")
async def history_remove1(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    conn = await get_conn()
    try:
        await remove_history_item(conn, user["user_uid"], video_id)
    finally:
        await release_conn(conn)
    ref = request.headers.get("referer") or "/history"
    return RedirectResponse(ref, status_code=302)

@router.post("/history/remove")
async def history_remove(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    ctype = (request.headers.get("content-type") or "").lower()
    raw = await request.body()
    ##print("[HISTORY RAW]", raw[:200])
    ##print("[CSRF NAME]", settings.CSRF_COOKIE_NAME)
    csrf_token = ""
    video_id = None
    if "application/x-www-form-urlencoded" in ctype:
        from urllib.parse import parse_qs
        parsed = parse_qs(raw.decode("utf-8", "ignore"), keep_blank_values=True)
        csrf_token = (parsed.get("csrf_token", [""])[0] or "").strip()
        video_id = (parsed.get("video_id", [""])[0] or "").strip() or None
    else:
        form = await request.form()
        csrf_token = (form.get("csrf_token") or "").strip()
        video_id = (form.get("video_id") or "").strip() or None

    ##print("[HISTORY MANUAL]", "csrf=", csrf_token, "video_id=", video_id)

    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)

    if not video_id:
        return HTMLResponse("<h1>Missing video_id</h1>", status_code=400)

    conn = await get_conn()
    try:
        await remove_history_item(conn, user["user_uid"], video_id)
    finally:
        await release_conn(conn)
    ref = request.headers.get("referer") or "/history"
    return RedirectResponse(ref, status_code=302)