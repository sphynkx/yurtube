from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_video
from db.users_db import get_user_by_uid
from services.comments.comment_create_srv import create_comment

router = APIRouter(prefix="/comments", tags=["comments"])


class CreateCommentIn(BaseModel):
    video_id: str
    text: str
    parent_id: Optional[str] = None
    reply_to_user_uid: Optional[str] = None


@router.post("/create")
async def create_comment_api(request: Request, data: CreateCommentIn) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    current_uid = str(user["user_uid"])

    conn = await get_conn()
    try:
        vrow = await get_video(conn, data.video_id)
        user_row = await get_user_by_uid(conn, current_uid)
    finally:
        await release_conn(conn)

    if not vrow:
        raise HTTPException(status_code=404, detail="video_not_found")

    enriched_user: Dict[str, Any] = {"user_uid": current_uid}
    if user_row and user_row.get("username"):
        enriched_user["username"] = user_row["username"]

    res = await create_comment(
        data.video_id,
        enriched_user,
        data.text,
        data.parent_id,
    )
    if isinstance(res, dict) and "error" in res:
        raise HTTPException(status_code=400, detail=res)
    return res