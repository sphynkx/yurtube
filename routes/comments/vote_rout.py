from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from services.comments.comment_vote_srv import apply_vote
from utils.security_ut import get_current_user

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
        likes, dislikes, my_vote = await apply_vote(data.video_id, user["user_uid"], data.comment_id, data.vote)
        return {"ok": True, "likes": likes, "dislikes": dislikes, "my_vote": my_vote, "user_id": user["user_uid"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})