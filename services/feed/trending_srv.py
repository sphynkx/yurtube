import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import get_conn, release_conn
from db.trending_db import count_public_videos_in_window, fetch_trending_rows, fetch_recent_public_rows
from utils.url_ut import build_storage_url


def _date_str(dt: Any) -> Optional[str]:
    if isinstance(dt, datetime.datetime):
        return dt.strftime("%Y-%m-%d")
    try:
        return str(dt) if dt is not None else None
    except Exception:
        return None


async def fetch_trending_page(limit: int, offset: int, days: int) -> Tuple[List[Dict[str, Any]], int]:
    """
    Trending without history: exponential decay by video age, inside a strict window.
    """
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    days = max(1, min(int(days), 365))

    conn = await get_conn()
    try:
        total = await count_public_videos_in_window(conn, days)
        if total == 0:
            return [], 0

        rows = await fetch_trending_rows(conn, limit, offset, days)
    finally:
        await release_conn(conn)

    items: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        items.append(
            {
                "video_id": d.get("video_id"),
                "title": d.get("title") or "",
                "description": d.get("description") or "",
                "author": (d.get("username") or "").strip() or (d.get("channel_id") or ""),
                "category": d.get("category") or "",
                "views_count": int(d.get("views_count") or 0),
                "likes_count": int(d.get("likes_count") or 0),
                "uploaded_at": _date_str(d.get("created_at")),
                "thumb_url": build_storage_url(d["thumb_asset_path"]) if d.get("thumb_asset_path") else None,
                "thumb_url_anim": build_storage_url(d["thumb_anim_asset_path"]) if d.get("thumb_anim_asset_path") else None,
                "avatar_url": build_storage_url(d["avatar_asset_path"]) if d.get("avatar_asset_path") else None,
                "score": float(d.get("score") or 0.0),
            }
        )
    return items, total


async def fetch_trending(limit: int = 12, days: int = 7) -> List[Dict[str, Any]]:
    items, _ = await fetch_trending_page(limit=limit, offset=0, days=days)
    return items


async def fetch_recent_public(limit: int = 12) -> List[Dict[str, Any]]:
    """
    Recent public videos, ordered by created_at desc.
    DB access delegated to db.trending_db.fetch_recent_public_rows.
    """
    limit = max(1, min(int(limit), 50))

    conn = await get_conn()
    try:
        rows = await fetch_recent_public_rows(conn, limit)
    finally:
        await release_conn(conn)

    items: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        items.append(
            {
                "video_id": d.get("video_id"),
                "title": d.get("title") or "",
                "description": d.get("description") or "",
                "author": (d.get("username") or "").strip() or (d.get("channel_id") or ""),
                "category": d.get("category") or "",
                "views_count": int(d.get("views_count") or 0),
                "likes_count": int(d.get("likes_count") or 0),
                "uploaded_at": _date_str(d.get("created_at")),
                "thumb_url": build_storage_url(d["thumb_asset_path"]) if d.get("thumb_asset_path") else None,
                "thumb_url_anim": build_storage_url(d["thumb_anim_asset_path"]) if d.get("thumb_anim_asset_path") else None,
                "avatar_url": build_storage_url(d["avatar_asset_path"]) if d.get("avatar_asset_path") else None,
            }
        )
    return items