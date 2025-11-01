from typing import Any, Dict, Optional
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import list_latest_public_videos
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.thumbs_ut import DEFAULT_THUMB_DATA_URI
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


def _augment(vrow: Dict[str, Any]) -> Dict[str, Any]:
    v = dict(vrow)
    thumb_path = v.get("thumb_asset_path")
    v["thumb_url"] = build_storage_url(thumb_path) if thumb_path else DEFAULT_THUMB_DATA_URI

    if thumb_path and "/" in thumb_path:
        anim_rel = thumb_path.rsplit("/", 1)[0] + "/thumb_anim.webp"
        abs_anim = os.path.join(settings.STORAGE_ROOT, anim_rel)
        v["thumb_anim_url"] = build_storage_url(anim_rel) if os.path.isfile(abs_anim) else None
    else:
        v["thumb_anim_url"] = None

    v["author_avatar_url_small"] = _avatar_small_url(v.get("avatar_asset_path"))
    return v


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    conn = await get_conn()
    try:
        rows = await list_latest_public_videos(conn, limit=24)
    finally:
        await release_conn(conn)

    user: Optional[Dict[str, str]] = get_current_user(request)
    videos = [_augment(dict(r)) for r in rows]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "videos": videos, "current_user": user},
    )