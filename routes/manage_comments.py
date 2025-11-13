from __future__ import annotations
from typing import Dict, Any, List, Optional, Set

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from config.config import settings
from db import get_conn, release_conn
from db.videos_query_db import get_owned_video_full as db_get_owned_video_full
from utils.security_ut import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _db_get_comment_settings(video_id: str) -> Dict[str, Any]:
    """
    Return per-video settings:
      {
        "comments_enabled": bool,
        "hide_deleted": "none"|"owner"|"all"
      }
    TODO: load from DB.
    """
    return {"comments_enabled": True, "hide_deleted": "all"}


def _db_save_comment_settings(video_id: str, comments_enabled: bool, hide_deleted: str, actor_uid: str) -> None:
    """
    Upsert per-video settings.
    TODO: save into DB.
    """
    return None


def _db_list_video_commenters(video_id: str) -> List[Dict[str, Any]]:
    """
    Return unique commenters for the video with ban flags:
    [
      {
        "uid": "user123",
        "name": "Display Name" | None,
        "avatar": "/path/to/avatar.png" | None,
        "comments_count": 5,
        "soft_ban": True|False,
        "hard_ban": True|False
      },
      ...
    ]
    TODO: query comments + join per-video ban table.
    """
    return []


def _db_save_comment_ban(video_id: str, user_uid: str, soft_ban: bool, hard_ban: bool, actor_uid: str) -> None:
    """
    Upsert per-video user ban flags.
    TODO: upsert ban row.
    """
    return None


def _db_get_video_soft_banned_uids(video_id: str) -> Set[str]:
    """
    Return set of user UIDs with soft_ban=True for video_id.
    TODO: query ban table.
    """
    return set()


@router.get("/manage/comments", response_class=HTMLResponse)
async def comments_admin_page(request: Request, v: str = Query(..., alias="v")) -> Any:
    """
    Admin page for video comments.
    """
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


# ---------------------------
# API models
# ---------------------------

class SettingsPost(BaseModel):
    video_id: str = Field(..., min_length=1)
    comments_enabled: bool = True
    hide_deleted: str = Field("all", pattern="^(none|owner|all)$")


class BanPost(BaseModel):
    video_id: str = Field(..., min_length=1)
    user_uid: str = Field(..., min_length=1)
    soft_ban: bool = False
    hard_ban: bool = False


# ---------------------------
# API: settings
# ---------------------------

@router.get("/api/manage/comments/settings")
async def api_comments_settings_get(request: Request, v: str = Query(..., alias="v")) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = (v or "").strip()
    if not video_id:
        return JSONResponse({"ok": False, "error": "missing video_id"}, status_code=400)

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    finally:
        await release_conn(conn)

    settings_doc = _db_get_comment_settings(video_id)
    return {"ok": True, "settings": settings_doc}


@router.post("/api/manage/comments/settings")
async def api_comments_settings_post(request: Request, payload: SettingsPost) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = payload.video_id.strip()
    hide_deleted = payload.hide_deleted.strip()
    comments_enabled = bool(payload.comments_enabled)

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    finally:
        await release_conn(conn)

    if hide_deleted not in ("none", "owner", "all"):
        return JSONResponse({"ok": False, "error": "bad hide_deleted"}, status_code=400)

    _db_save_comment_settings(video_id, comments_enabled, hide_deleted, user["user_uid"])
    return {"ok": True}


# ---------------------------
# API: users list and bans
# ---------------------------

@router.get("/api/manage/comments/users")
async def api_comments_users_get(request: Request, v: str = Query(..., alias="v")) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = (v or "").strip()
    if not video_id:
        return JSONResponse({"ok": False, "error": "missing video_id"}, status_code=400)

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    finally:
        await release_conn(conn)

    users = _db_list_video_commenters(video_id)
    return {"ok": True, "users": users}


@router.post("/api/manage/comments/ban")
async def api_comments_ban_post(request: Request, payload: BanPost) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    video_id = payload.video_id.strip()
    user_uid = payload.user_uid.strip()

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    finally:
        await release_conn(conn)

    _db_save_comment_ban(video_id, user_uid, bool(payload.soft_ban), bool(payload.hard_ban), user["user_uid"])
    return {"ok": True}


# ---------------------------
# Helpers for your public /comments/list
# ---------------------------

def inject_comments_enabled(video_id: str, payload: Dict[str, Any]) -> None:
    """
    Attach comments_enabled flag into /comments/list payload.
    """
    settings_doc = _db_get_comment_settings(video_id)
    payload["comments_enabled"] = bool(settings_doc.get("comments_enabled", True))


def apply_comment_policies(video_id: str, requester_uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply hide_deleted and soft_ban with reparenting to nearest alive ancestor.

    Expected payload shape before filtering:
      {
        "ok": True,
        "roots": [cid, ...],
        "children_map": { parent_cid: [child_cid, ...], ... } | optional
        "comments": {
          cid: {
            "parent_id": <cid|null>,
            "visible": True|False,
            "tombstone": True|False (optional),
            "author_uid": "uid",
            ...
          }, ...
        },
        "texts": {...},
        "avatars": {...}
      }
    """
    settings_doc = _db_get_comment_settings(video_id)
    hide_deleted = str(settings_doc.get("hide_deleted", "all"))

    comments: Dict[str, Dict[str, Any]] = dict(payload.get("comments") or {})
    # roots not strictly needed here; we will recompute
    soft_banned = _db_get_video_soft_banned_uids(video_id)

    # children by parent_id
    children: Dict[Optional[str], List[str]] = {}
    for cid, meta in comments.items():
        pid = meta.get("parent_id")
        children.setdefault(pid, []).append(cid)

    def is_tomb(meta: Dict[str, Any]) -> bool:
        if "tombstone" in meta:
            return bool(meta.get("tombstone"))
        if meta.get("visible") is False:
            return True
        return False

    # owner visibility policy requires knowing if requester is owner; to keep helper generic,
    # assume owner check is done by the caller (if needed). If you need owner-only behavior,
    # pass through a precomputed flag in payload or adapt this helper.
    requester_is_owner = payload.get("_requester_is_owner") is True

    to_remove: Set[str] = set()
    for cid, meta in comments.items():
        a_uid = str(meta.get("author_uid") or "")
        if a_uid in soft_banned:
            to_remove.add(cid)
            continue
        if is_tomb(meta):
            if hide_deleted == "none":
                to_remove.add(cid)
            elif hide_deleted == "owner" and not requester_is_owner:
                to_remove.add(cid)

    if not to_remove:
        out = dict(payload)
        out["children_map"] = _build_children_map(comments)
        return out

    # unlink removed from their parents
    for rid in to_remove:
        pid = comments.get(rid, {}).get("parent_id")
        if pid in children:
            children[pid] = [x for x in children[pid] if x != rid]

    # find nearest alive ancestor of the removed node
    def nearest_alive(parent_id: Optional[str]) -> Optional[str]:
        cur = parent_id
        while cur is not None:
            if cur not in to_remove:
                return cur
            cur = comments.get(cur, {}).get("parent_id")
        return None

    # reparent removed node children to nearest alive ancestor of the removed node
    for rid in list(to_remove):
        for child in list(children.get(rid, []) or []):
            new_parent = nearest_alive(comments.get(rid, {}).get("parent_id"))
            comments[child]["parent_id"] = new_parent
            children.setdefault(new_parent, []).append(child)
        children[rid] = []

    # remove nodes
    for rid in to_remove:
        comments.pop(rid, None)

    # recompute roots and children_map
    new_roots = [cid for cid, meta in comments.items() if meta.get("parent_id") is None]
    new_children_map = _build_children_map(comments)

    out = dict(payload)
    out["roots"] = new_roots
    out["comments"] = comments
    out["children_map"] = new_children_map
    return out


def _build_children_map(comments: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for cid, meta in comments.items():
        pid = meta.get("parent_id")
        if pid is None:
            continue
        mapping.setdefault(pid, []).append(cid)
    return mapping