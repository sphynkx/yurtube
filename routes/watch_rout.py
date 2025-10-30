from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.views_db import add_view, increment_video_views_counter
from db.videos_db import get_video
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt


@router.get("/watch", response_class=HTMLResponse)
async def watch(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    conn = await get_conn()
    try:
        video = await get_video(conn, v)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Count a view (MVP: count on page load)
        user = get_current_user(request)
        user_uid: Optional[str] = user["user_uid"] if user else None
        await add_view(conn, video_id=v, user_uid=user_uid, duration_sec=0)
        await increment_video_views_counter(conn, video_id=v)
    finally:
        await release_conn(conn)

    user = get_current_user(request)
    return templates.TemplateResponse(
        "watch.html",
        {"request": request, "video": video, "current_user": user},
    )