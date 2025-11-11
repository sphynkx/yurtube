from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from utils.security_ut import get_current_user
from services.comments.comment_update_srv import update_comment_text, soft_delete_comment

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
    res = await update_comment_text(data.video_id, data.comment_id, user["user_uid"], data.text)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res)
    return res

@router.post("/delete")
async def delete_comment_api(request: Request, data: DeleteCommentIn) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    res = await soft_delete_comment(data.video_id, data.comment_id, user["user_uid"])
    if "error" in res:
        raise HTTPException(status_code=400, detail=res)
    return res