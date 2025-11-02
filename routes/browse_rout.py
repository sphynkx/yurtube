from typing import Any, Dict, Optional
import os

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.subscriptions_db import list_subscriptions
from db.videos_db import (
    list_history_distinct_latest,
    list_trending_public_videos,
)
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
from utils.url_ut import build_storage_url
from services.feed.trending_srv import fetch_trending, fetch_recent_public, fetch_trending_page

router = APIRouter()
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


def _thumb_url(thumb_path: Optional[str]) -> str:
    return build_storage_url(thumb_path) if thumb_path else DEFAULT_THUMB_DATA_URI


def _anim_url_existing(thumb_path: Optional[str]) -> Optional[str]:
    if thumb_path and "/" in thumb_path:
        anim_rel = thumb_path.rsplit("/", 1)[0] + "/thumb_anim.webp"
        abs_anim = os.path.join(settings.STORAGE_ROOT, anim_rel)
        if os.path.isfile(abs_anim):
            return build_storage_url(anim_rel)
    return None


def _page_args(page: int, per_page: int) -> Dict[str, int]:
    p = max(1, page)
    pp = max(1, min(per_page, 50))
    return {"limit": pp, "offset": (p - 1) * pp, "page": p, "per_page": pp}


# replace the existing /trending handler with this one
@router.get("/trending", response_class=HTMLResponse)
async def trending(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    days: int = Query(7, ge=1, le=365),
) -> Any:
    # normalize days to typical buckets 1/7/30; accept any value but map UI to these
    bucket = days
    if days in (1, 7, 30):
        bucket = days
    elif days < 3:
        bucket = 1
    elif days < 15:
        bucket = 7
    else:
        bucket = 30

    limit = per_page
    offset = (page - 1) * per_page

    videos, total = await fetch_trending_page(limit=limit, offset=offset, days=bucket)
    last_page = max(1, (total + per_page - 1) // per_page)

    # build small window of page numbers around current page
    start = max(1, page - 2)
    end = min(last_page, page + 2)
    page_numbers = list(range(start, end + 1))

    return templates.TemplateResponse(
        "trending.html",
        {
            "request": request,
            "current_user": get_current_user(request),
            "videos": videos,
            "videos_count": len(videos),
            "total": total,
            "page": page,
            "per_page": per_page,
            "last_page": last_page,
            "page_numbers": page_numbers,
            "days": bucket,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> Any:
    user = get_current_user(request)
    if not user:
        return templates.TemplateResponse(
            "subscriptions.html",
            {"request": request, "current_user": None, "channels": [], "need_login": True},
        )

    conn = await get_conn()
    try:
        rows = await list_subscriptions(conn, user["user_uid"])
        channels = []
        for r in rows:
            d = dict(r)
            d["avatar_url_small"] = _avatar_small_url(d.get("avatar_asset_path"))
            channels.append(d)
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "subscriptions.html",
        {
            "request": request,
            "current_user": user,
            "channels": channels,
            "need_login": False,
            "page": page,
            "per_page": per_page,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def history(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=50),
) -> Any:
    args = _page_args(page, per_page)
    user = get_current_user(request)
    if not user:
        return templates.TemplateResponse(
            "history.html",
            {"request": request, "current_user": None, "videos": [], "need_login": True},
        )

    conn = await get_conn()
    try:
        rows = await list_history_distinct_latest(conn, user["user_uid"], args["limit"], args["offset"])
        videos = []
        for r in rows:
            v = dict(r)
            v["author_avatar_url_small"] = _avatar_small_url(v.get("avatar_asset_path"))
            v["thumb_url"] = _thumb_url(v.get("thumb_asset_path"))
            v["thumb_anim_url"] = _anim_url_existing(v.get("thumb_asset_path"))
            videos.append(v)
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "current_user": user,
            "videos": videos,
            "need_login": False,
            "page": args["page"],
            "per_page": args["per_page"],
        },
    )