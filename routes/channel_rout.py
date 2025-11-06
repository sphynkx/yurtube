from typing import Any, Dict, List, Optional
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.subscriptions_db import (
    count_subscribers,
    is_subscribed,
    subscribe,
    unsubscribe,
    list_subscribers,
)
from db.videos_db import (
    list_author_public_videos,
)
from db.users_db import get_user_by_name_or_channel as db_get_user_by_name_or_channel
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
from utils.url_ut import build_storage_url

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


def _augment(vrow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add presentation fields for a video card on channel page.
    """
    v = dict(vrow)
    thumb_path = v.get("thumb_asset_path")
    v["thumb_url"] = build_storage_url(thumb_path) if thumb_path else DEFAULT_THUMB_DATA_URI

    # Animated preview only if file exists
    if thumb_path and "/" in thumb_path:
        anim_rel = thumb_path.rsplit("/", 1)[0] + "/thumb_anim.webp"
        abs_anim = os.path.join(settings.STORAGE_ROOT, anim_rel)
        v["thumb_anim_url"] = build_storage_url(anim_rel) if os.path.isfile(abs_anim) else None
    else:
        v["thumb_anim_url"] = None

    v["author_avatar_url_small"] = _avatar_small_url(v.get("avatar_asset_path"))
    return v


async def _get_user_by_name_or_channel(conn, name_or_channel: str) -> Optional[Dict[str, Any]]:
    """
    Fetch channel owner by @username or channel_id.
    Includes avatar asset path when present.

    NOTE: DB access is delegated to db.users_db.get_user_by_name_or_channel.
    """
    return await db_get_user_by_name_or_channel(conn, name_or_channel)


async def _render_channel(request: Request, owner: Optional[Dict[str, Any]]) -> HTMLResponse:
    user = get_current_user(request)
    if not owner:
        return templates.TemplateResponse(
            "channel.html",
            {
                "request": request,
                "current_user": user,
                "owner": None,
                "videos": [],
                "subscribers": 0,
                "subscribed": False,
            },
            status_code=404,
        )

    conn = await get_conn()
    try:
        subs_cnt = await count_subscribers(conn, owner["user_uid"])
        subd = False
        if user and user.get("user_uid"):
            subd = await is_subscribed(conn, user["user_uid"], owner["user_uid"])

        rows = await list_author_public_videos(conn, owner["user_uid"], limit=100, offset=0)
        videos = [_augment(dict(r)) for r in rows]
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "channel.html",
        {
            "request": request,
            "current_user": user,
            "owner": owner,
            "videos": videos,
            "subscribers": subs_cnt,
            "subscribed": subd,
        },
    )


@router.get("/@{username}", response_class=HTMLResponse)
async def channel_by_username(request: Request, username: str) -> Any:
    conn = await get_conn()
    try:
        owner = await _get_user_by_name_or_channel(conn, username)
    finally:
        await release_conn(conn)
    return await _render_channel(request, owner)


# Support both the new path "/c/{channel_id}" and the legacy "/channel/{channel_id}"
@router.get("/c/{channel_id}", response_class=HTMLResponse)
@router.get("/channel/{channel_id}", response_class=HTMLResponse)
async def channel_by_id(request: Request, channel_id: str) -> Any:
    conn = await get_conn()
    try:
        owner = await _get_user_by_name_or_channel(conn, channel_id)
    finally:
        await release_conn(conn)
    return await _render_channel(request, owner)


# Subscribers lists: support @username, /c/{id} and legacy /channel/{id}
@router.get("/@{name}/subscribers", response_class=HTMLResponse)
@router.get("/c/{name}/subscribers", response_class=HTMLResponse)
@router.get("/channel/{name}/subscribers", response_class=HTMLResponse)
async def channel_subscribers(request: Request, name: str) -> Any:
    """
    Simple subscribers list page without a dedicated template.
    """
    user = get_current_user(request)

    conn = await get_conn()
    try:
        owner = await _get_user_by_name_or_channel(conn, name)
        if not owner:
            return HTMLResponse(content="<h1>Channel not found</h1>", status_code=404)

        subs_rows = await list_subscribers(conn, owner["user_uid"])
        items: List[str] = []
        for r in subs_rows:
            d = dict(r)
            if d.get("username"):
                link = f"/@{d['username']}"
                label = f"@{d['username']}"
            else:
                link = f"/c/{d['channel_id']}"
                label = d["channel_id"]
            items.append(f'<li><a href="{link}">{label}</a></li>')

        back_link = f'/@{owner["username"]}' if owner.get("username") else f'/c/{owner["channel_id"]}'
        back_label = f'@{owner["username"]}' if owner.get("username") else owner["channel_id"]

        html = [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><title>Subscribers</title></head><body>",
            f"<h1>Subscribers of {back_label}</h1>",
            "<ul>",
            *items,
            "</ul>",
            f'<p><a href="{back_link}">Back to channel</a></p>',
            "</body></html>",
        ]
        return HTMLResponse(content="".join(html), status_code=200)
    finally:
        await release_conn(conn)


@router.post("/channel/subscribe")
async def post_subscribe(request: Request, channel_uid: str = Form(...)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        await subscribe(conn, user["user_uid"], channel_uid)
    finally:
        await release_conn(conn)

    ref = request.headers.get("referer") or "/"
    return RedirectResponse(ref, status_code=302)


@router.post("/channel/unsubscribe")
async def post_unsubscribe(request: Request, channel_uid: str = Form(...)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        await unsubscribe(conn, user["user_uid"], channel_uid)
    finally:
        await release_conn(conn)

    ref = request.headers.get("referer") or "/"
    return RedirectResponse(ref, status_code=302)