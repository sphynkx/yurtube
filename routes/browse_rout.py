from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.videos_db import (
    list_history_distinct_latest,
    list_subscription_feed,
    list_trending_public_videos,
)
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
from utils.url_ut import build_storage_url

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt


def _augment(vrow: Dict[str, Any]) -> Dict[str, Any]:
    thumb_path = vrow.get("thumb_asset_path")
    v = dict(vrow)
    v["thumb_url"] = build_storage_url(thumb_path) if thumb_path else DEFAULT_THUMB_DATA_URI
    return v


@router.get("/trending", response_class=HTMLResponse)
async def trending(request: Request) -> Any:
    conn = await get_conn()
    try:
        rows = await list_trending_public_videos(conn, limit=24)
        videos = [_augment(dict(r)) for r in rows]
    finally:
        await release_conn(conn)

    user: Optional[Dict[str, str]] = get_current_user(request)
    return templates.TemplateResponse(
        "trending.html",
        {"request": request, "current_user": user, "videos": videos},
    )


@router.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return templates.TemplateResponse(
            "subscriptions.html",
            {"request": request, "current_user": None, "videos": [], "need_login": True},
        )

    conn = await get_conn()
    try:
        rows = await list_subscription_feed(conn, user["user_uid"], limit=50)
        videos = [_augment(dict(r)) for r in rows]
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "subscriptions.html",
        {"request": request, "current_user": user, "videos": videos, "need_login": False},
    )


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return templates.TemplateResponse(
            "history.html",
            {"request": request, "current_user": None, "videos": [], "need_login": True},
        )

    conn = await get_conn()
    try:
        rows = await list_history_distinct_latest(conn, user["user_uid"], limit=50)
        videos = [_augment(dict(r)) for r in rows]
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "history.html",
        {"request": request, "current_user": user, "videos": videos, "need_login": False},
    )