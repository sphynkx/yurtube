from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from utils.security_ut import get_current_user

from services.ytcomments.client_srv import get_ytcomments_client, UserContext

from services.notifications.events_pub import publish

router = APIRouter(prefix="/comments", tags=["comments"])


class VoteIn(BaseModel):
    video_id: str
    comment_id: str
    vote: int


@router.post("/vote")
async def vote_comment(data: VoteIn, request: Request, user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail={"error": "auth required"})

    video_id = (data.video_id or "").strip()
    comment_id = (data.comment_id or "").strip()
    vote = int(data.vote or 0)
    if vote not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail={"error": "invalid vote"})

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

    # Publish only if vote became like
    if res.get("my_vote") == 1:
        try:
            publish(
                "comment.voted",
                {
                    "video_id": video_id,
                    "comment_id": comment_id,
                    "actor_uid": str(user["user_uid"]),
                    "comment_author_uid": None,  # without extra RPC we don't know it yet
                    "vote": 1,
                },
            )
        except Exception:
            pass

    return {
        "ok": True,
        "likes": int(res.get("likes", 0)),
        "dislikes": int(res.get("dislikes", 0)),
        "my_vote": int(res.get("my_vote", 0)),
        "user_id": str(user["user_uid"]),
    }