from typing import Any, Dict, Optional

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.channels_db import get_user_by_channel_id, get_user_by_username
from db.subscriptions_db import (
    count_subscribers,
    is_subscribed,
    list_subscribers,
    subscribe,
    unsubscribe,
)
from db.videos_db import list_author_public_videos
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


@router.get("/@{username}", response_class=HTMLResponse)
async def channel_by_username(request: Request, username: str) -> Any:
    conn = await get_conn()
    try:
        owner = await get_user_by_username(conn, username)
        if not owner:
            raise HTTPException(status_code=404, detail="Channel not found")

        rows = await list_author_public_videos(conn, owner["user_uid"], limit=24, offset=0)
        videos = [_augment(dict(r)) for r in rows]

        user = get_current_user(request)
        subs_count = await count_subscribers(conn, owner["user_uid"])
        subscribed = bool(user and await is_subscribed(conn, user["user_uid"], owner["user_uid"]))
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "channel.html",
        {
            "request": request,
            "current_user": get_current_user(request),
            "owner": owner,
            "subscribers": subs_count,
            "subscribed": subscribed,
            "videos": videos,
        },
    )


@router.get("/c/{channel_id}", response_class=HTMLResponse)
async def channel_by_id(request: Request, channel_id: str) -> Any:
    conn = await get_conn()
    try:
        owner = await get_user_by_channel_id(conn, channel_id)
        if not owner:
            raise HTTPException(status_code=404, detail="Channel not found")

        rows = await list_author_public_videos(conn, owner["user_uid"], limit=24, offset=0)
        videos = [_augment(dict(r)) for r in rows]

        user = get_current_user(request)
        subs_count = await count_subscribers(conn, owner["user_uid"])
        subscribed = bool(user and await is_subscribed(conn, user["user_uid"], owner["user_uid"]))
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "channel.html",
        {
            "request": request,
            "current_user": get_current_user(request),
            "owner": owner,
            "subscribers": subs_count,
            "subscribed": subscribed,
            "videos": videos,
        },
    )


@router.get("/channel/subscribers", response_class=HTMLResponse)
async def channel_subscribers(request: Request, channel_uid: str) -> Any:
    user = get_current_user(request)
    if not user or user["user_uid"] != channel_uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = await get_conn()
    try:
        items = await list_subscribers(conn, channel_uid)
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "channel_subscribers.html",
        {
            "request": request,
            "current_user": user,
            "subscribers": items,
        },
    )


@router.post("/channel/subscribe")
async def post_subscribe(request: Request, channel_uid: str = Form(...)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    conn = await get_conn()
    try:
        await subscribe(conn, user["user_uid"], channel_uid)
    finally:
        await release_conn(conn)

    referer = request.headers.get("referer") or "/"
    return RedirectResponse(referer, status_code=status.HTTP_302_FOUND)


@router.post("/channel/unsubscribe")
async def post_unsubscribe(request: Request, channel_uid: str = Form(...)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    conn = await get_conn()
    try:
        await unsubscribe(conn, user["user_uid"], channel_uid)
    finally:
        await release_conn(conn)

    referer = request.headers.get("referer") or "/"
    return RedirectResponse(referer, status_code=status.HTTP_302_FOUND)