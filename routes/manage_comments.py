"""
Manage comments admin for a specific video (FastAPI).

Routes:
- GET  /manage/comments?v=<video_id>
- GET  /api/manage/comments/settings?v=<video_id>
- POST /api/manage/comments/settings
- GET  /api/manage/comments/users?v=<video_id>
- POST /api/manage/comments/ban

Persists:
- comments_enabled via videos.allow_comments
- hide_deleted via videos.embed_params['comments_hide_deleted']
- per-user bans via videos.embed_params arrays:
    comments_soft_ban_uids, comments_hard_ban_uids
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

import json
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from config.config import settings
from db import get_conn, release_conn
from db.videos_query_db import (
    get_owned_video_full as db_get_owned_video_full,
    set_video_allow_comments as db_set_video_allow_comments,
    set_video_comments_hide_deleted as db_set_video_comments_hide_deleted,
    set_video_embed_params_raw as db_set_video_embed_params_raw,
)
from db.videos_db import get_video as db_get_video
from db.user_assets_db import get_user_avatar_path
from db.users_db import get_usernames_by_uids
from utils.url_ut import build_storage_url
from utils.security_ut import get_current_user

from services.comments.comment_tree_srv import fetch_root, build_tree_payload

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/manage/comments", response_class=HTMLResponse)
async def comments_admin_page(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    video_id = (v or "").strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="missing video_id")

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "manage/comments.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "current_user": user,
            "video_id": video_id,
        },
        headers={"Cache-Control": "no-store"},
    )


class SettingsPost(BaseModel):
    video_id: str = Field(..., min_length=12, max_length=12)
    comments_enabled: bool = True
    hide_deleted: str = Field("all", pattern="^(none|owner|all)$")


class BanPost(BaseModel):
    video_id: str = Field(..., min_length=12, max_length=12)
    user_uid: str = Field(..., min_length=1)
    soft_ban: bool = False
    hard_ban: bool = False


@router.get("/api/manage/comments/settings")
async def api_comments_settings_get(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = (v or "").strip()
    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

        row = await db_get_video(conn, video_id)
        comments_enabled = bool(row.get("allow_comments", True)) if row else True

        hide_deleted = "all"
        if row:
            ep = row.get("embed_params")
            if isinstance(ep, str):
                try:
                    ep = json.loads(ep) if ep.strip() else {}
                except Exception:
                    ep = {}
            if isinstance(ep, dict):
                hv = str(ep.get("comments_hide_deleted", "") or "").strip()
                if hv in ("none", "owner", "all"):
                    hide_deleted = hv

        return {"ok": True, "settings": {"comments_enabled": comments_enabled, "hide_deleted": hide_deleted}}
    finally:
        await release_conn(conn)


@router.post("/api/manage/comments/settings")
async def api_comments_settings_post(request: Request, payload: SettingsPost) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = payload.video_id.strip()
    hide_deleted = payload.hide_deleted.strip()

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

        await db_set_video_allow_comments(conn, video_id, bool(payload.comments_enabled))
        await db_set_video_comments_hide_deleted(conn, video_id, hide_deleted)

        return {"ok": True}
    finally:
        await release_conn(conn)


@router.get("/api/manage/comments/users")
async def api_comments_users_get(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = (v or "").strip()

    root = await fetch_root(video_id)
    if not root:
        return {"ok": True, "users": []}

    payload = build_tree_payload(root, current_uid=user["user_uid"], show_hidden=True)

    counts: Dict[str, int] = {}
    for cid, meta in (payload.get("comments") or {}).items():
        uid = meta.get("author_uid")
        if not uid:
            continue
        counts[uid] = counts.get(uid, 0) + 1

    soft_set: set = set()
    hard_set: set = set()

    conn = await get_conn()
    names: Dict[str, str] = {}
    avatars: Dict[str, str] = {}
    try:
        row = await db_get_video(conn, video_id)
        ep = row.get("embed_params") if row else None
        if isinstance(ep, str):
            try:
                ep = json.loads(ep) if ep.strip() else {}
            except Exception:
                ep = {}
        if isinstance(ep, dict):
            s_list = ep.get("comments_soft_ban_uids") or []
            h_list = ep.get("comments_hard_ban_uids") or []
            if isinstance(s_list, list):
                soft_set = set([str(x).strip() for x in s_list if isinstance(x, str)])
            if isinstance(h_list, list):
                hard_set = set([str(x).strip() for x in h_list if isinstance(x, str)])

        uids = list(counts.keys())
        if uids:
            names = await get_usernames_by_uids(conn, uids)
            for au in uids:
                p = await get_user_avatar_path(conn, au)
                avatars[au] = build_storage_url(p) if p else "/static/img/avatar_default.svg"
    finally:
        await release_conn(conn)

    users: List[Dict[str, Any]] = []
    for uid, cnt in counts.items():
        users.append({
            "uid": uid,
            "name": (names.get(uid) or uid),
            "avatar": avatars.get(uid) or "/static/img/avatar_default.svg",
            "comments_count": int(cnt),
            "soft_ban": uid in soft_set,
            "hard_ban": uid in hard_set,
        })

    users.sort(key=lambda x: (-x["comments_count"], x["uid"]))
    return {"ok": True, "users": users}


@router.post("/api/manage/comments/ban")
async def api_comments_ban_post(request: Request, payload: BanPost) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = payload.video_id.strip()
    target_uid = str(payload.user_uid).strip()
    new_soft = bool(payload.soft_ban)
    new_hard = bool(payload.hard_ban)

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

        row = await db_get_video(conn, video_id)
        ep: Dict[str, Any] = {}
        if row:
            raw = row.get("embed_params")
            if isinstance(raw, str):
                try:
                    ep = json.loads(raw) if raw.strip() else {}
                except Exception:
                    ep = {}
            elif isinstance(raw, dict):
                ep = dict(raw)
        if not isinstance(ep, dict):
            ep = {}

        s_list = ep.get("comments_soft_ban_uids")
        h_list = ep.get("comments_hard_ban_uids")
        if not isinstance(s_list, list):
            s_list = []
        if not isinstance(h_list, list):
            h_list = []

        def add_or_remove(lst: List[str], uid: str, on: bool) -> List[str]:
            s = set([str(x).strip() for x in lst if isinstance(x, str)])
            if on:
                s.add(uid)
            else:
                s.discard(uid)
            return sorted([x for x in s if x])

        ep["comments_soft_ban_uids"] = add_or_remove(s_list, target_uid, new_soft)
        ep["comments_hard_ban_uids"] = add_or_remove(h_list, target_uid, new_hard)

        await db_set_video_embed_params_raw(conn, video_id, ep)
        return {"ok": True}
    finally:
        await release_conn(conn)