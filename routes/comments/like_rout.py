from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

from utils.security_ut import get_current_user
from services.ytcomments.client_srv import get_ytcomments_client, UserContext

router = APIRouter(prefix="/comments", tags=["comments"])


class LikeIn(BaseModel):
    video_id: str
    comment_id: str
    delta_like: int = 0
    delta_dislike: int = 0


@router.post("/like")
async def like_comment(data: LikeIn, request: Request, user=Depends(get_current_user)) -> Dict[str, Any]:
    """
    Legacy endpoint kept for compatibility.
    Internally translated to ytcomments Vote RPC.
      - delta_like=+1  -> vote=+1
      - delta_dislike=+1 -> vote=-1
      - anything else -> vote=0
    """
    if not user:
        raise HTTPException(status_code=401, detail={"error": "auth required"})

    video_id = (data.video_id or "").strip()
    comment_id = (data.comment_id or "").strip()
    if not video_id or not comment_id:
        raise HTTPException(status_code=400, detail={"error": "missing video_id/comment_id"})

    dl = int(data.delta_like or 0)
    dd = int(data.delta_dislike or 0)

    vote = 0
    if dl > 0 and dd <= 0:
        vote = 1
    elif dd > 0 and dl <= 0:
        vote = -1
    else:
        vote = 0

    ctx = UserContext(
        user_uid=str(user["user_uid"]),
        username=str(user.get("username") or "") or None,
        channel_id=str(user.get("channel_id") or "") or None,
        ip=(request.client.host if request.client else None),
        user_agent=str(request.headers.get("user-agent") or "") or None,
    )

    client = get_ytcomments_client()
    res = await client.vote(video_id=video_id, comment_id=comment_id, vote=vote, ctx=ctx)
    if not res:
        raise HTTPException(status_code=502, detail={"error": "ytcomments vote failed"})

    return {
        "ok": True,
        "likes": int(res.get("likes", 0) or 0),
        "dislikes": int(res.get("dislikes", 0) or 0),
        "my_vote": int(res.get("my_vote", 0) or 0),
    }