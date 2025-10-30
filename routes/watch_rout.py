from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.videos_db import get_video
from utils.security_ut import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/watch", response_class=HTMLResponse)
async def watch(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    conn = await get_conn()
    try:
        video = await get_video(conn, v)
    finally:
        await release_conn(conn)

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    user = get_current_user(request)
    return templates.TemplateResponse(
        "watch.html",
        {"request": request, "video": video, "current_user": user},
    )