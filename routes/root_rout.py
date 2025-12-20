from typing import Any, Dict, Optional, List, Tuple
import os
import asyncio
import inspect

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import list_latest_public_videos_count, list_latest_public_videos
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
from utils.url_ut import build_storage_url

# --- Pagination utilities ---
from utils.pagination_ut import normalize_page, normalize_page_size, build_page_range

# --- Storage abstraction ---
from services.ytstorage.base_srv import StorageClient


router = APIRouter(tags=["root"])
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt
templates.env.globals["sitename"] = settings.SITENAME
templates.env.globals["support_email"] = settings.SUPPORT_EMAIL


def _avatar_small_url(avatar_path: Optional[str]) -> str:
    if not avatar_path:
        return "/static/img/avatar_default.svg"
    if avatar_path.endswith("avatar.png"):
        small_rel = avatar_path[: -len("avatar.png")] + "avatar_small.png"
    else:
        small_rel = avatar_path
    return build_storage_url(small_rel)


async def _storage_exists(storage_client: StorageClient, rel: str) -> bool:
    """
    Safe exists check supporting both async and sync implementations.
    """
    fn = getattr(storage_client, "exists", None)
    if not callable(fn):
        return False
    res = fn(rel)
    if inspect.isawaitable(res):
        try:
            return bool(await res)
        except Exception:
            return False
    try:
        return bool(res)
    except Exception:
        return False


def _with_ver(url: Optional[str], ver: Optional[int]) -> Optional[str]:
    if not url:
        return url
    try:
        v = int(ver or 0)
    except Exception:
        v = 0
    if v <= 0:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={v}"


async def _augment(vrow: Dict[str, Any], storage_client: StorageClient) -> Dict[str, Any]:
    v = dict(vrow)
    thumb_path = v.get("thumb_asset_path")
    ver = v.get("thumb_pref_offset")
    v["thumb_url"] = _with_ver(build_storage_url(thumb_path), ver) if thumb_path else DEFAULT_THUMB_DATA_URI

    # Prefer explicit DB asset path for animated preview, fall back to legacy static name.
    anim_asset = v.get("thumb_anim_asset_path")
    if anim_asset:
        v["thumb_anim_url"] = _with_ver(build_storage_url(anim_asset), ver)
    elif thumb_path and "/" in thumb_path:
        anim_rel = thumb_path.rsplit("/", 1)[0] + "/thumb_anim.webp"
        exists = await _storage_exists(storage_client, anim_rel)
        v["thumb_anim_url"] = _with_ver(build_storage_url(anim_rel), ver) if exists else None
    else:
        v["thumb_anim_url"] = None

    v["author_avatar_url_small"] = _avatar_small_url(v.get("avatar_asset_path"))
    return v



@router.get("/", response_class=HTMLResponse)
async def index(
        request: Request,
        page: Optional[int] = Query(default=1, ge=1),
        page_size: Optional[int] = Query(default=24, ge=6, le=96),
    ) -> Any:
    # Pagination
    page = normalize_page(page)
    page_size = normalize_page_size(page_size)
    offset = (page - 1) * page_size

    conn = await get_conn()
    try:
        total = await list_latest_public_videos_count(conn)  # get all public videos amount
        rows = await list_latest_public_videos(conn, limit=page_size, offset=offset)
    finally:
        await release_conn(conn)

    # Compute pagination
    total_pages = max(1, (total + page_size - 1) // page_size)
    has_prev = page > 1
    has_next = page < total_pages
    page_range: List[Tuple[str, Optional[int]]] = build_page_range(page, total_pages, window=2)

    # Storage client
    storage_client: StorageClient = request.app.state.storage

    # Augment rows with URLs
    videos: List[Dict[str, Any]] = []
    for r in rows:
        try:
            videos.append(await _augment(dict(r), storage_client))
        except Exception:
            videos.append(dict(r))

    context = {
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_tagline": settings.BRAND_TAGLINE,
        "favicon_url": settings.FAVICON_URL,
        "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        "request": request,
        "current_user": get_current_user(request),
        "videos": videos,
        "videos_count": len(videos),
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "page_range": page_range,
    }
    return templates.TemplateResponse("index.html", context)