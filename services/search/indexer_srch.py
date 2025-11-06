import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from db import get_conn, release_conn
from services.search.search_client_srch import get_backend
from db.search_index_db import fetch_video_for_index

log = logging.getLogger(__name__)

async def _fetch_video(conn, video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch video row for indexing.

    NOTE: DB access is delegated to db.search_index_db.fetch_video_for_index.
    """
    return await fetch_video_for_index(conn, video_id)

def _author_from_row(row: Dict[str, Any]) -> str:
    u = (row.get("username") or "").strip() if row.get("username") else ""
    return u or ((row.get("channel_id") or "").strip())

def _to_unix(dt) -> int:
    try:
        import datetime
        if isinstance(dt, datetime.datetime):
            return int(dt.timestamp())
        return int(dt or 0)
    except Exception:
        return 0

async def reindex_video(video_id: str) -> Tuple[bool, str]:
    try:
        conn = await get_conn()
        try:
            row = await _fetch_video(conn, video_id)
            if not row:
                msg = f"video not found: {video_id}"
                log.warning("reindex_video: %s", msg)
                return False, msg
            doc = {
                "video_id": row["video_id"],
                "title": row.get("title") or "",
                "description": row.get("description") or "",
                "status": row.get("status") or "public",
                "created_at_unix": _to_unix(row.get("created_at")),
                "views_count": int(row.get("views_count") or 0),
                "likes_count": int(row.get("likes_count") or 0),
                "category": row.get("category") or "",
                "author": _author_from_row(row),
                "tags": [],
                "lang": "",
            }
        finally:
            await release_conn(conn)

        backend = get_backend()
        ok, msg = await backend.index_video(doc)  # type: ignore[attr-defined]
        if ok:
            log.info("reindex_video: indexed %s", video_id)
            return True, ""
        else:
            log.error("reindex_video: index failed for %s: %s", video_id, msg)
            return False, msg
    except Exception as e:
        log.exception("reindex_video: failed for %s: %s", video_id, e)
        return False, repr(e)

async def delete_from_index(video_id: str) -> Tuple[bool, str]:
    try:
        backend = get_backend()
        ok, msg = await backend.delete_video(video_id)  # type: ignore[attr-defined]
        if ok:
            log.info("delete_from_index: deleted %s", video_id)
            return True, ""
        else:
            log.error("delete_from_index: failed %s: %s", video_id, msg)
            return False, msg
    except Exception as e:
        log.exception("delete_from_index: failed for %s: %s", video_id, e)
        return False, repr(e)

def fire_and_forget_reindex(video_id: str) -> None:
    try:
        asyncio.create_task(reindex_video(video_id))
    except RuntimeError:
        log.warning("fire_and_forget_reindex: no event loop for %s", video_id)