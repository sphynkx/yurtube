import secrets
from typing import Any, List, Optional
import os
import asyncio

from fastapi import APIRouter, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import count_history_distinct_latest, list_history_distinct_latest
from db.history_db import clear_history, remove_history_item
from utils.url_ut import build_storage_url
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
from utils.format_ut import fmt_dt

# --- Pagination utilities ---
from utils.pagination_ut import normalize_page, normalize_page_size, build_page_range

# --- Storage abstraction ---
from services.ytstorage.base_srv import StorageClient

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt
templates.env.globals["sitename"] = settings.SITENAME


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
    if not cookie_tok or not form_tok:
        return False
    try:
        import secrets as _sec
        return _sec.compare_digest(cookie_tok, form_tok)
    except Exception:
        return False


# --- Helpers ---

async def _augment(vrow: dict, storage_client: StorageClient) -> dict:
    v = dict(vrow)
    tap = v.get("thumb_asset_path")
    v["thumb_url"] = build_storage_url(tap) if tap else DEFAULT_THUMB_DATA_URI
    if tap and "/" in tap:
        anim_rel = tap.rsplit("/", 1)[0] + "/thumb_anim.webp"
        v["thumb_anim_url"] = build_storage_url(anim_rel) if await storage_client.exists(anim_rel) else None
    else:
        v["thumb_anim_url"] = None
    return v


# --- GET /history ---

@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    page: Optional[int] = Query(default=1, ge=1),
    page_size: Optional[int] = Query(default=24, ge=6, le=96),
) -> Any:
    user = get_current_user(request)
    csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()

    if not user:
        resp = templates.TemplateResponse(
            "history.html",
            {
                "request": request,
                "current_user": None,
                "need_login": True,
                "videos": [],
                "csrf_token": csrf_token,
                "page": 1,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "has_prev": False,
                "has_next": False,
                "prev_page": None,
                "next_page": None,
                "page_items": [],
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

    page = normalize_page(page)
    page_size = normalize_page_size(page_size)
    offset = (page - 1) * page_size

    conn = await get_conn()
    try:
        total = await count_history_distinct_latest(conn, user["user_uid"])
        rows = await list_history_distinct_latest(conn, user["user_uid"], limit=page_size, offset=offset)
        storage_client: StorageClient = request.app.state.storage
        videos = await asyncio.gather(*[_augment(dict(r), storage_client) for r in rows])
    finally:
        await release_conn(conn)

    # Compute pagination
    total_pages = max(1, (total + page_size - 1) // page_size)
    has_prev = page > 1
    has_next = page < total_pages

    # Build page items
    page_items_raw = build_page_range(page, total_pages, window=2)
    page_items: List[Dict[str, Any]] = []
    for kind, num in page_items_raw:
        if kind == "ellipsis":
            page_items.append({"kind": "ellipsis"})
        else:
            page_items.append({
                "kind": "number",
                "num": num,
                "current": (num == page),
                "url": f"/history?page={num}&page_size={page_size}",
            })

    resp = templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "current_user": user,
            "need_login": False,
            "videos": videos,
            "csrf_token": csrf_token,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next,
            "prev_page": (page - 1) if has_prev else None,
            "next_page": (page + 1) if has_next else None,
            "page_items": page_items,
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