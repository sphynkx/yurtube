from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_video
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

    # Load video info to get its author (will be moderator)
    conn = await get_conn()
    try:
        vrow = await get_video(conn, data.video_id)
    finally:
        await release_conn(conn)

    if not vrow:
        raise HTTPException(status_code=404, detail="video_not_found")

    author_uid_video = str(vrow["author_uid"])
    current_uid = str(user["user_uid"])
    is_owner_moderator = (current_uid == author_uid_video)

    author_name = user.get("username") or "User"

    res = await create_comment(
        video_id=data.video_id,
        author_uid=current_uid,
        author_name=author_name,
        parent_id=data.parent_id,
        raw_text=data.text,
        reply_to_user_uid=data.reply_to_user_uid,
        is_owner_moderator=is_owner_moderator
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res)
    return res