from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_video
from db.users_db import get_user_by_uid

from services.ytcomments.client_srv import get_ytcomments_client, UserContext

# Notifications publish
from services.notifications.events_pub import publish

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

    username = ""
    if user_row and user_row.get("username"):
        username = str(user_row["username"] or "")

    # TODO: if you have channel_id in user profile, pass it here too
    ctx = UserContext(
        user_uid=current_uid,
        username=username or None,
        channel_id=None,
        ip=(request.client.host if request.client else None),
        user_agent=str(request.headers.get("user-agent") or "") or None,
    )

    client = get_ytcomments_client()
    dto = await client.create_comment(
        video_id=data.video_id,
        text=data.text,
        parent_id=data.parent_id or "",
        ctx=ctx,
        idempotency_key="",  # can be wired from frontend later
    )
    if not dto:
        raise HTTPException(status_code=502, detail="ytcomments_create_failed")

    # Publish notification event (best-effort)
    try:
        publish(
            "comment.created",
            {
                "video_id": data.video_id,
                "comment_id": dto.id,
                "actor_uid": current_uid,
                "parent_comment_author_uid": None,  # no direct lookup without extra RPC
                "text_preview": (data.text or "")[:160],
            },
        )
    except Exception:
        pass

    # Response format: keep it simple and compatible with old code
    return {
        "ok": True,
        "comment_id": dto.id,
        "video_id": dto.video_id,
        "parent_id": dto.parent_id,
        "text": dto.content_raw,
        "created_at": dto.created_at_ms,
        "updated_at": dto.updated_at_ms,
        "author_uid": dto.user_uid,
        "author_name": dto.username or dto.channel_id or "",
    }