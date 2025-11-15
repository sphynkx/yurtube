from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.reactions_db import set_video_reaction, get_video_reaction_state

router = APIRouter(prefix="/videos", tags=["reactions"])

class ReactIn(BaseModel):
    video_id: str
    # -1 = dislike, 0 = none (remove), 1 = like
    reaction: int

@router.post("/react")
async def react_video(data: ReactIn, request: Request, user=Depends(get_current_user)) -> Any:
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    if data.reaction not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="invalid_reaction")

    conn = await get_conn()
    try:
        likes, dislikes, my = await set_video_reaction(conn, user["user_uid"], data.video_id, data.reaction)
        return {"ok": True, "likes": likes, "dislikes": dislikes, "my_reaction": my}
    finally:
        await release_conn(conn)

@router.get("/react/state")
async def react_state(
    request: Request,
    video_id: str = Query(...),
) -> Any:
    user = get_current_user(request)
    conn = await get_conn()
    try:
        state = await get_video_reaction_state(conn, user["user_uid"] if user else None, video_id)
        return {"ok": True, **state}
    finally:
        await release_conn(conn)