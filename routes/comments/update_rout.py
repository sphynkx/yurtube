from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from utils.security_ut import get_current_user
from services.ytcomments.client_srv import get_ytcomments_client, UserContext
from db import get_conn, release_conn
from db.videos_db import get_video

router = APIRouter(prefix="/comments", tags=["comments"])


class UpdateCommentIn(BaseModel):
    video_id: str
    comment_id: str
    text: str


class DeleteCommentIn(BaseModel):
    video_id: str
    comment_id: str
    hard_delete: bool = False


@router.post("/update")
async def update_comment_api(request: Request, data: UpdateCommentIn) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    uid = str(user["user_uid"])
    client = get_ytcomments_client()
    ctx = UserContext(
        user_uid=uid,
        username=str(user.get("username") or "") or None,
        channel_id=str(user.get("channel_id") or "") or None,
        ip=(request.client.host if request.client else None),
        user_agent=str(request.headers.get("user-agent") or "") or None,
    )

    dto = await client.edit_comment(
        video_id=data.video_id,
        comment_id=data.comment_id,
        text=data.text,
        ctx=ctx,
    )
    if not dto:
        raise HTTPException(status_code=502, detail="ytcomments_edit_failed")

    return {
        "ok": True,
        "video_id": dto.video_id,
        "comment_id": dto.id,
        "text": dto.content_raw,
        "edited": bool(dto.edited),
        "updated_at": int(dto.updated_at_ms),
    }


@router.post("/delete")
async def delete_comment_api(request: Request, data: DeleteCommentIn) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    uid = str(user["user_uid"])

    # Determine moderator (author of video)
    is_moderator = False
    conn = await get_conn()
    try:
        v = await get_video(conn, data.video_id)
        if v and str(v.get("author_uid") or "") == uid:
            is_moderator = True
    finally:
        await release_conn(conn)

    client = get_ytcomments_client()
    ctx = UserContext(
        user_uid=uid,
        username=str(user.get("username") or "") or None,
        channel_id=str(user.get("channel_id") or "") or None,
        is_moderator=bool(is_moderator),
        is_video_owner=bool(is_moderator),
        ip=(request.client.host if request.client else None),
        user_agent=str(request.headers.get("user-agent") or "") or None,
    )

    dto = await client.delete_comment(
        video_id=data.video_id,
        comment_id=data.comment_id,
        hard_delete=bool(data.hard_delete),
        ctx=ctx,
    )
    if not dto:
        raise HTTPException(status_code=502, detail="ytcomments_delete_failed")

    return {
        "ok": True,
        "video_id": dto.video_id,
        "comment_id": dto.id,
        "is_deleted": bool(dto.is_deleted),
        "hard_delete": bool(data.hard_delete),
        "updated_at": int(dto.updated_at_ms),
    }