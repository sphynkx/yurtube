from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException

from db import get_conn, release_conn
from utils.security_ut import get_current_user
from db.videos_query_db import get_owned_video_full as db_get_owned_video_full
from db.video_renditions_db import list_video_renditions

router = APIRouter()

@router.get("/internal/ytconvert/renditions")
async def ytconvert_list_renditions(request: Request, video_id: str) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        return {"ok": False, "error": "auth_required"}

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        renditions = await list_video_renditions(conn, video_id)
    finally:
        await release_conn(conn)

    return {"ok": True, "renditions": renditions}