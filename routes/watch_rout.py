from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.assets_db import get_thumbnail_asset_path
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


def _base_url(request: Request) -> str:
    if settings.BASE_URL:
        return settings.BASE_URL.rstrip("/")
    xf_proto = request.headers.get("x-forwarded-proto")
    xf_host = request.headers.get("x-forwarded-host")
    if xf_host:
        scheme = (xf_proto or "https").split(",")[0].strip()
        host = xf_host.split(",")[0].strip()
        return f"{scheme}://{host}"
    return f"{request.url.scheme}://{request.url.netloc}"


def _boolish(val: Optional[str]) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on", "y", "t"):
        return True
    if s in ("0", "false", "no", "off", "n", "f"):
        return False
    # numeric strings
    try:
        return int(s) != 0
    except ValueError:
        return False


def _int_or_zero(val: Optional[str]) -> int:
    try:
        return max(0, int(str(val).strip()))
    except Exception:
        return 0


@router.get("/watch", response_class=HTMLResponse)
async def watch(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    conn = await get_conn()
    try:
        video = await get_video(conn, v)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        thumb_rel = await get_thumbnail_asset_path(conn, v)
        poster_url = build_storage_url(thumb_rel) if thumb_rel else None

        user = get_current_user(request)
        user_uid: Optional[str] = user["user_uid"] if user else None
        await add_view(conn, video_id=v, user_uid=user_uid, duration_sec=0)
        await increment_video_views_counter(conn, video_id=v)
    finally:
        await release_conn(conn)

    user = get_current_user(request)
    vdict = dict(video)
    vdict["author_avatar_url_small"] = _avatar_small_url(vdict.get("avatar_asset_path"))
    embed_url = _base_url(request) + f"/embed?v={v}"
    embed_code = f'<iframe src="{embed_url}" width="560" height="315" frameborder="0" allowfullscreen></iframe>'
    return templates.TemplateResponse(
        "watch.html",
        {
            "request": request,
            "video": vdict,
            "current_user": user,
            "embed_code": embed_code,
            "poster_url": poster_url,
        },
    )


@router.get("/embed", response_class=HTMLResponse)
async def embed(
    request: Request,
    v: Optional[str] = Query(None),
    autoplay: Optional[str] = Query(None),
    mute: Optional[str] = Query(None),
    loop: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    width: Optional[str] = Query(None),
    height: Optional[str] = Query(None),
) -> Any:
    """
    Minimal embed page.
    Accepts bool-like params: 1/0, true/false, yes/no, on/off, y/n, t/f.
    No JSON errors to end-users: show placeholder if invalid.
    """
    is_valid_id = isinstance(v, str) and len(v) == 12
    video_row = None
    poster_url: str = "/static/img/embed_missing.svg"
    src_url: Optional[str] = None

    conn = await get_conn()
    try:
        if is_valid_id:
            video_row = await get_video(conn, v)  # type: ignore[arg-type]
            if video_row:
                thumb_rel = await get_thumbnail_asset_path(conn, v)  # type: ignore[arg-type]
                if thumb_rel:
                    poster_url = build_storage_url(thumb_rel)
                src_url = f"/storage/{video_row['storage_path']}/original.webm"
                start_sec = _int_or_zero(start)
                if start_sec > 0:
                    src_url = f"{src_url}#t={start_sec}"
    finally:
        await release_conn(conn)

    auto_attr = "autoplay" if _boolish(autoplay) else ""
    mute_attr = "muted" if _boolish(mute) else ""
    loop_attr = "loop" if _boolish(loop) else ""

    return templates.TemplateResponse(
        "embed.html",
        {
            "request": request,
            "video": dict(video_row) if video_row else None,
            "poster_url": poster_url,
            "src_url": src_url,
            "auto_attr": auto_attr,
            "mute_attr": mute_attr,
            "loop_attr": loop_attr,
        },
    )