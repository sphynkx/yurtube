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

# --- Storage abstraction ---
from services.ytstorage.base_srv import StorageClient

router = APIRouter(tags=["root"])
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt


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


async def _augment(vrow: Dict[str, Any], storage_client: StorageClient) -> Dict[str, Any]:
    v = dict(vrow)
    thumb_path = v.get("thumb_asset_path")
    v["thumb_url"] = build_storage_url(thumb_path) if thumb_path else DEFAULT_THUMB_DATA_URI

    if thumb_path and "/" in thumb_path:
        anim_rel = thumb_path.rsplit("/", 1)[0] + "/thumb_anim.webp"
        v["thumb_anim_url"] = build_storage_url(anim_rel) if await _storage_exists(storage_client, anim_rel) else None
    else:
        v["thumb_anim_url"] = None

    v["author_avatar_url_small"] = _avatar_small_url(v.get("avatar_asset_path"))
    return v


def _normalize_page(page: Optional[int]) -> int:
    try:
        p = int(page or 1)
    except Exception:
        p = 1
    return 1 if p < 1 else p


def _normalize_page_size(ps: Optional[int]) -> int:
    try:
        v = int(ps or 24)
    except Exception:
        v = 24
    if v < 6:
        v = 6
    if v > 96:
        v = 96
    return v


def _build_page_range(current: int, total_pages: int, window: int = 2) -> List[Tuple[str, Optional[int]]]:
    """
    Returns the range of pages to display:
    - Always show the first and last pages.
    - Show the neighborhood around the current page: current-window .. current+window.
    - Insert '...' (ellipsis) between non-consecutive segments.
    Elements are returned as ("number", n) or ("ellipsis", None).
    """
    if total_pages <= 1:
        return [("number", 1)]

    pages: List[int] = []
    pages.append(1)
    start = max(2, current - window)
    end = min(total_pages - 1, current + window)
    for p in range(start, end + 1):
        pages.append(p)
    pages.append(total_pages)

    # Remove dups, and sort
    pages = sorted(set(pages))

    # Build with ellipsis
    result: List[Tuple[str, Optional[int]]] = []
    prev = None
    for p in pages:
        if prev is not None and p != prev + 1:
            result.append(("ellipsis", None))
        result.append(("number", p))
        prev = p
    return result


@router.get("/", response_class=HTMLResponse)
async def index(
        request: Request,
        page: Optional[int] = Query(default=1, ge=1),
        page_size: Optional[int] = Query(default=24, ge=6, le=96),
    ) -> Any:
    # Pagination
    page = _normalize_page(page)
    page_size = _normalize_page_size(page_size)
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
    # Build pages range with ellipsises, curr page keeps at center
    page_items_raw = _build_page_range(page, total_pages, window=2)
    page_items: List[Dict[str, Any]] = []
    for kind, num in page_items_raw:
        if kind == "ellipsis":
            page_items.append({"kind": "ellipsis"})
        else:
            page_items.append({
                "kind": "number",
                "num": num,
                "current": (num == page),
                "url": f"/?page={num}&page_size={page_size}",
            })

    user: Optional[Dict[str, str]] = get_current_user(request)
    storage_client: StorageClient = request.app.state.storage  # mark: uses StorageClient for augment
    #videos = [_augment(dict(r), storage_client) for r in rows]
    videos = await asyncio.gather(*[_augment(dict(r), storage_client) for r in rows])

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "videos": videos,
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
            "current_user": user,
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
        },
    )