from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from services.comments.comment_like_srv import like_delta

router = APIRouter(prefix="/comments", tags=["comments"])


class LikeIn(BaseModel):
    video_id: str
    comment_id: str
    delta_like: int = 0
    delta_dislike: int = 0


@router.post("/like")
async def like_comment(data: LikeIn) -> Dict[str, Any]:
    res = await like_delta(data.video_id, data.comment_id, data.delta_like, data.delta_dislike)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res)
    return res