from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_video

from services.ytcomments.client_srv import get_ytcomments_client, UserContext

router = APIRouter(prefix="/comments", tags=["comments"])


class UpdateCommentIn(BaseModel):
    video_id: str
    comment_id: str
    text: str


class DeleteCommentIn(BaseModel):
    video_id: str
    comment_id: str


@router.post("/update")
async def update_comment_api(request: Request, data: UpdateCommentIn) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    video_id = (data.video_id or "").strip()
    comment_id = (data.comment_id or "").strip()
    if not video_id or not comment_id:
        raise HTTPException(status_code=400, detail="invalid_args")

    # Moderator = author of video (as before)
    is_video_owner = False
    conn = await get_conn()
    try:
        v = await get_video(conn, video_id)
        if v and v.get("author_uid") == user["user_uid"]:
            is_video_owner = True
    finally:
        await release_conn(conn)

    ctx = UserContext(
        user_uid=str(user["user_uid"]),
        username=str(user.get("username") or "") or None,
        channel_id=str(user.get("channel_id") or "") or None,
        is_video_owner=bool(is_video_owner),
        is_moderator=bool(is_video_owner),
        ip=(request.client.host if request.client else None),
        user_agent=str(request.headers.get("user-agent") or "") or None,
    )

    client = get_ytcomments_client()
    dto = await client.edit_comment(
        video_id=video_id,
        comment_id=comment_id,
        text=data.text or "",
        ctx=ctx,
    )
    if not dto:
        raise HTTPException(status_code=502, detail="ytcomments_edit_failed")

    return {
        "ok": True,
        "comment_id": dto.id,
        "video_id": dto.video_id,
        "parent_id": dto.parent_id,
        "text": dto.content_raw,
        "edited": bool(dto.edited),
        "created_at": dto.created_at_ms,
        "updated_at": dto.updated_at_ms,
        "is_deleted": bool(dto.is_deleted),
    }


@router.post("/delete")
async def delete_comment_api(request: Request, data: DeleteCommentIn) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    video_id = (data.video_id or "").strip()
    comment_id = (data.comment_id or "").strip()
    if not video_id or not comment_id:
        raise HTTPException(status_code=400, detail="invalid_args")

    # Moderator (author of video)
    is_video_owner = False
    conn = await get_conn()
    try:
        v = await get_video(conn, video_id)
        if v and v.get("author_uid") == user["user_uid"]:
            is_video_owner = True
    finally:
        await release_conn(conn)

    ctx = UserContext(
        user_uid=str(user["user_uid"]),
        username=str(user.get("username") or "") or None,
        channel_id=str(user.get("channel_id") or "") or None,
        is_video_owner=bool(is_video_owner),
        is_moderator=bool(is_video_owner),
        ip=(request.client.host if request.client else None),
        user_agent=str(request.headers.get("user-agent") or "") or None,
    )

    client = get_ytcomments_client()
    # Keep old semantics: /comments/delete is SOFT delete
    dto = await client.delete_comment(
        video_id=video_id,
        comment_id=comment_id,
        hard_delete=False,
        ctx=ctx,
    )
    if not dto:
        raise HTTPException(status_code=502, detail="ytcomments_delete_failed")

    return {
        "ok": True,
        "comment_id": dto.id,
        "video_id": dto.video_id,
        "is_deleted": bool(dto.is_deleted),
        "updated_at": dto.updated_at_ms,
    }