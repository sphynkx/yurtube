from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.videos_db import list_latest_public_videos
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
from utils.url_ut import build_storage_url

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt


def _augment_with_thumb(vrow: Dict[str, Any]) -> Dict[str, Any]:
    thumb_path = vrow.get("thumb_asset_path")
    v = dict(vrow)
    v["thumb_url"] = build_storage_url(thumb_path) if thumb_path else DEFAULT_THUMB_DATA_URI
    return v


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    conn = await get_conn()
    try:
        videos = await list_latest_public_videos(conn, limit=24)
    finally:
        await release_conn(conn)

    user: Optional[Dict[str, str]] = get_current_user(request)
    videos_aug = [_augment_with_thumb(dict(v)) for v in videos]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "videos": videos_aug,
            "current_user": user,
        },
    )