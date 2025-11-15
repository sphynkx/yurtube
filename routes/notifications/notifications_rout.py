from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from typing import Any, Dict, List

from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.notifications_db import (
    list_notifications,
    unread_count,
    mark_read,
    mark_all_read,
    get_user_prefs,
    set_user_prefs,
)
from config.notifications_config import notifications_config

router = APIRouter(prefix="/notifications", tags=["notifications"])


class MarkReadIn(BaseModel):
    ids: List[str]


class PrefItem(BaseModel):
    type: str
    inapp: bool
    email: bool = False
    allow_unlisted: bool | None = None


class SetPrefsIn(BaseModel):
    prefs: List[PrefItem]


@router.get("/list")
async def notifications_list(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    if not notifications_config.ENABLED:
        return {"ok": True, "notifications": [], "unread": 0}

    conn = await get_conn()
    try:
        rows = await list_notifications(conn, user["user_uid"], limit, offset)
        items = []
        for r in rows:
            items.append(
                {
                    "notif_id": str(r["notif_id"]),
                    "type": r["type"],
                    "payload": r["payload"],
                    "created_at": r["created_at"].isoformat(),
                    "read_at": r["read_at"].isoformat() if r["read_at"] else None,
                }
            )
        uc = await unread_count(conn, user["user_uid"])
        return {"ok": True, "notifications": items, "unread": uc}
    finally:
        await release_conn(conn)


@router.get("/unread-count")
async def notifications_unread_count(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    if not notifications_config.ENABLED:
        return {"ok": True, "unread": 0}
    conn = await get_conn()
    try:
        uc = await unread_count(conn, user["user_uid"])
        return {"ok": True, "unread": uc}
    finally:
        await release_conn(conn)


@router.post("/mark-read")
async def notifications_mark_read(request: Request, data: MarkReadIn) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    conn = await get_conn()
    try:
        cnt = await mark_read(conn, user["user_uid"], data.ids)
        uc = await unread_count(conn, user["user_uid"])
        return {"ok": True, "updated": cnt, "unread": uc}
    finally:
        await release_conn(conn)


@router.post("/mark-all-read")
async def notifications_mark_all_read(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    conn = await get_conn()
    try:
        cnt = await mark_all_read(conn, user["user_uid"])
        return {"ok": True, "updated": cnt, "unread": 0}
    finally:
        await release_conn(conn)


@router.get("/prefs")
async def notifications_get_prefs(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    conn = await get_conn()
    try:
        prefs = await get_user_prefs(conn, user["user_uid"])
        # Merge with defaults (fill missing)
        merged = {}
        for k in notifications_config.DEFAULT_INAPP.keys():
            existing = prefs.get(k)
            if existing:
                merged[k] = existing
            else:
                merged[k] = {
                    "inapp": notifications_config.DEFAULT_INAPP.get(k, True),
                    "email": notifications_config.DEFAULT_EMAIL.get(k, False),
                    "allow_unlisted": None,
                }
        return {"ok": True, "prefs": merged}
    finally:
        await release_conn(conn)


@router.post("/prefs")
async def notifications_set_prefs(request: Request, data: SetPrefsIn) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    conn = await get_conn()
    try:
        items = [p.dict() for p in data.prefs]
        await set_user_prefs(conn, user["user_uid"], items)
        prefs = await get_user_prefs(conn, user["user_uid"])
        return {"ok": True, "prefs": prefs}
    finally:
        await release_conn(conn)