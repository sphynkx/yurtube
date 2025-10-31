from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.views_db import add_view, increment_video_views_counter
from db.videos_db import get_video
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt


def _avatar_small_url(avatar_path: Optional[str]) -> str:
    if not avatar_path:
        return "/static/img/avatar_default.svg"
    if avatar_path.endswith("avatar.png"):
        small_rel = avatar_path[: -len("avatar.png")] + "avatar_small.png"
    else:
        small_rel = avatar_path
    return build_storage_url(small_rel)


@router.get("/watch", response_class=HTMLResponse)
async def watch(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    conn = await get_conn()
    try:
        video = await get_video(conn, v)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        user = get_current_user(request)
        user_uid: Optional[str] = user["user_uid"] if user else None
        await add_view(conn, video_id=v, user_uid=user_uid, duration_sec=0)
        await increment_video_views_counter(conn, video_id=v)
    finally:
        await release_conn(conn)

    user = get_current_user(request)
    vdict = dict(video)
    vdict["author_avatar_url_small"] = _avatar_small_url(vdict.get("avatar_asset_path"))
    return templates.TemplateResponse(
        "watch.html",
        {"request": request, "video": vdict, "current_user": user},
    )