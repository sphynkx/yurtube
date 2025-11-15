from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from services.comments.comment_vote_srv import apply_vote
from utils.security_ut import get_current_user

from services.notifications.events_pub import publish
from db.comments.mongo_conn import root_coll

router = APIRouter(prefix="/comments", tags=["comments"])


class VoteIn(BaseModel):
    video_id: str
    comment_id: str
    vote: int


@router.post("/vote")
async def vote_comment(data: VoteIn, request: Request, user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail={"error": "auth required"})
    try:
        likes, dislikes, my_vote = await apply_vote(
            data.video_id, user["user_uid"], data.comment_id, data.vote
        )

        # Publish only if vote got the like
        if my_vote == 1:
            try:
                root = await root_coll().find_one({"video_id": data.video_id})
                if root and isinstance(root.get("comments"), dict):
                    meta = root["comments"].get(data.comment_id)
                    if meta and isinstance(meta, dict):
                        comment_author_uid = meta.get("author_uid")
                        if comment_author_uid and comment_author_uid != user["user_uid"]:
                            publish(
                                "comment.voted",
                                {
                                    "video_id": data.video_id,
                                    "comment_id": data.comment_id,
                                    "actor_uid": user["user_uid"],
                                    "comment_author_uid": comment_author_uid,
                                    "vote": 1,
                                },
                            )
            except Exception:
                pass

        return {
            "ok": True,
            "likes": likes,
            "dislikes": dislikes,
            "my_vote": my_vote,
            "user_id": user["user_uid"],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})