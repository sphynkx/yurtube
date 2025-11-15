import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.reactions_db import set_video_reaction, get_video_reaction_state
from services.notifications.events_pub import publish

logger = logging.getLogger("reactions")

router = APIRouter(prefix="/videos", tags=["reactions"])

class ReactIn(BaseModel):
    video_id: str
    reaction: int  # -1 dislike, 0 none, 1 like

@router.post("/react")
async def react_video(data: ReactIn, request: Request, user=Depends(get_current_user)) -> Any:
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    if data.reaction not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="invalid_reaction")

    conn = await get_conn()
    try:
        likes, dislikes, my = await set_video_reaction(conn, user["user_uid"], data.video_id, data.reaction)
        logger.info("Video reaction applied video_id=%s actor=%s reaction_in=%s final=%s likes=%s dislikes=%s",
                    data.video_id, user["user_uid"], data.reaction, my, likes, dislikes)
        if my == 1:
            row = await conn.fetchrow(
                "SELECT v.author_uid, v.title FROM videos v WHERE v.video_id = $1",
                data.video_id,
            )
            if not row:
                logger.warning("Video not found for like notification video_id=%s", data.video_id)
            else:
                author_uid = row["author_uid"]
                title = (row["title"] or "")[:160]
                if author_uid == user["user_uid"]:
                    logger.info("Skip like notification (author liked own video) video_id=%s", data.video_id)
                else:
                    logger.info("Publish video.reacted event video_id=%s actor=%s author=%s",
                                data.video_id, user["user_uid"], author_uid)
                    publish(
                        "video.reacted",
                        {
                            "video_id": data.video_id,
                            "actor_uid": user["user_uid"],
                            "video_author_uid": author_uid,
                            "title": title,
                            "reaction": "like",
                        },
                    )
        return {"ok": True, "likes": likes, "dislikes": dislikes, "my_reaction": my}
    finally:
        await release_conn(conn)

@router.get("/react/state")
async def react_state(request: Request, video_id: str = Query(...)) -> Any:
    user = get_current_user(request)
    conn = await get_conn()
    try:
        state = await get_video_reaction_state(conn, user["user_uid"] if user else None, video_id)
        return {"ok": True, **state}
    finally:
        await release_conn(conn)