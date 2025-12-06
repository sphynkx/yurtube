## SRTG_DONE
## SRTG_2MODIFY: build_storage_url(
## SRTG_2MODIFY: storage/
## SRTG_2MODIFY: _path
from typing import Any, Dict, List, Optional
import os
import json
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.assets_db import get_thumbnail_asset_path, get_thumbs_vtt_asset
from db.views_db import add_view, increment_video_views_counter
from db.videos_db import get_video
from db.videos_query_db import fetch_watch_video_full, fetch_embed_video_info
from services.feed.recommend_srv import fetch_rightbar_for_video  # right-bar recommendations
from utils.format_ut import fmt_dt
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

from db.assets_db import get_thumbs_vtt_asset

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["dt"] = fmt_dt
templates.env.globals["brand_logo_url"] = settings.BRAND_LOGO_URL
templates.env.globals["favicon_url"] = settings.FAVICON_URL
templates.env.globals["apple_touch_icon_url"] = settings.APPLE_TOUCH_ICON_URL


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
        if (scheme == "https" and host.endswith(":443")) or (scheme == "http" and host.endswith(":80")):
            host = host.rsplit(":", 1)[0]
        return f"{scheme}://{host}"

    scheme = request.url.scheme
    host = request.url.netloc
    if (scheme == "https" and host.endswith(":443")) or (scheme == "http" and host.endswith(":80")):
        host = host.rsplit(":", 1)[0]
    return f"{scheme}://{host}"


def _boolish(val: Optional[str]) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on", "y", "t"):
        return True
    if s in ("0", "false", "no", "off", "n", "f"):
        return False
    try:
        return int(s) != 0
    except Exception:
        return False


def _int_or_zero(val: Optional[str]) -> int:
    try:
        return max(0, int(str(val).strip()))
    except Exception:
        return 0


def _embed_defaults_from_row(vrow: Dict[str, Any]) -> Dict[str, int]:
    params = vrow.get("embed_params")
    if isinstance(params, str):
        try:
            params = json.loads(params) if params.strip() else {}
        except Exception:
            params = {}
    if not isinstance(params, dict):
        params = {}

    def pick_int(k: str, default_int: int) -> int:
        val = params.get(k, default_int)
        try:
            return int(val)
        except Exception:
            return default_int

    ap = pick_int("autoplay", getattr(settings, "EMBED_DEFAULT_AUTOPLAY", 0))
    mu = pick_int("mute", getattr(settings, "EMBED_DEFAULT_MUTE", 0))
    lo = pick_int("loop", getattr(settings, "EMBED_DEFAULT_LOOP", 0))
    st = pick_int("start", 0)
    return {"autoplay": 1 if ap else 0, "mute": 1 if mu else 0, "loop": 1 if lo else 0, "start": max(0, st)}


@router.get("/watch", response_class=HTMLResponse)
async def watch_page(request: Request, v: str) -> Any:
    user = get_current_user(request)
    conn = await get_conn()
    try:
        row = await fetch_watch_video_full(conn, v)
        video: Optional[Dict[str, Any]] = dict(row) if row else None

        caption_vtt: Optional[str] = video.get("captions_vtt") if video and video.get("captions_vtt") else None
        caption_lang: str = video.get("captions_lang") if video and video.get("captions_lang") else "auto"

        if not row:
            # Video not found
            subtitles: List[Dict[str, Any]] = []
            player_options: Dict[str, Any] = {"autoplay": False, "muted": False, "loop": False, "start": 0}
            embed_url = f"{_base_url(request)}/embed?v={v}"
            context = {
                "brand_logo_url": settings.BRAND_LOGO_URL,
                "brand_tagline": settings.BRAND_TAGLINE,
                "favicon_url": settings.FAVICON_URL,
                "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                "request": request,
                "current_user": user,
                "video": None,
                "video_id": v,
                "player_name": settings.VIDEO_PLAYER,
                "video_src": None,
                "poster_url": None,
                "thumb_anim_url": None,
                "avatar_url": None,
                "allow_embed": False,
                "embed_url": embed_url,
                "subtitles": subtitles,
                "player_options": player_options,
                "not_found": True,
                "fallback_image_url": settings.FALLBACK_PLACEHOLDER_URL,
                "sprites_vtt_url": None,
                "caption_vtt": caption_vtt,
                "caption_lang": caption_lang,
            }
            return templates.TemplateResponse("watch.html", context, headers={"Cache-Control": "no-store"})

        # Video found
        user_uid: Optional[str] = user["user_uid"] if user else None
        await add_view(conn, video_id=v, user_uid=user_uid, duration_sec=0)
        await increment_video_views_counter(conn, video_id=v)
        try:
            video["views_count"] = int(video.get("views_count") or 0) + 1
        except Exception:
            pass

        # Build web URL for video via abs path
        video_src = build_storage_url(video["storage_path"].strip("/").rstrip("/") + "/original.webm")
        poster_url = build_storage_url(video["thumb_asset_path"]) if video.get("thumb_asset_path") else None
        thumb_anim_url = build_storage_url(video["thumb_anim_asset_path"]) if video.get("thumb_anim_asset_path") else None
        avatar_url = build_storage_url(video["avatar_asset_path"]) if video.get("avatar_asset_path") else None
        video["avatar_url"] = avatar_url

        subtitles: List[Dict[str, Any]] = []
        player_options: Dict[str, Any] = {"autoplay": False, "muted": False, "loop": False, "start": 0}
        allow_embed = bool(video.get("allow_embed"))
        embed_url = f"{_base_url(request)}/embed?v={video['video_id']}"
        sprites_vtt_rel = await get_thumbs_vtt_asset(conn, video["video_id"])
        sprites_vtt_url = build_storage_url(sprites_vtt_rel) if sprites_vtt_rel else None

        recommended_videos: List[Dict[str, Any]] = []
        try:
            if getattr(settings, "RIGHTBAR_ENABLED", True):
                limit = int(getattr(settings, "RIGHTBAR_LIMIT", 12) or 12)
                recommended_videos = await fetch_rightbar_for_video(video["video_id"], user_uid, limit=limit)
        except Exception:
            recommended_videos = []

        context = {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "current_user": user,
            "video": video,
            "player_name": settings.VIDEO_PLAYER,
            "video_src": video_src,
            "poster_url": poster_url,
            "thumb_anim_url": thumb_anim_url,
            "avatar_url": avatar_url,
            "allow_embed": allow_embed,
            "embed_url": embed_url,
            "subtitles": subtitles,
            "player_options": player_options,
            "recommended_videos": recommended_videos,
            "sprites_vtt_url": sprites_vtt_url,
            "caption_vtt": caption_vtt,
            "caption_lang": caption_lang,
        }
        return templates.TemplateResponse("watch.html", context, headers={"Cache-Control": "no-store"})
    finally:
        await release_conn(conn)


@router.get("/embed", response_class=HTMLResponse)
async def embed_page(
    request: Request,
    v: str,
    t: int = 0,
    autoplay: int = 0,
    muted: int = 0,
    loop: int = 0
) -> Any:
    user = get_current_user(request)
    conn = await get_conn()
    try:
        row = await fetch_embed_video_info(conn, v)
        video: Optional[Dict[str, Any]] = dict(row) if row else None

        caption_vtt: Optional[str] = video.get("captions_vtt") if video and video.get("captions_vtt") else None
        caption_lang: str = video.get("captions_lang") if video and video.get("captions_lang") else "auto"

        if not video:
            subtitles: List[Dict[str, Any]] = []
            player_options: Dict[str, Any] = {
                "autoplay": bool(autoplay),
                "muted": bool(muted),
                "loop": bool(loop),
                "start": max(0, int(t or 0)),
            }
            context = {
                "brand_logo_url": settings.BRAND_LOGO_URL,
                "brand_tagline": settings.BRAND_TAGLINE,
                "favicon_url": settings.FAVICON_URL,
                "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                "request": request,
                "video": None,
                "player_name": settings.VIDEO_PLAYER,
                "video_src": None,
                "poster_url": None,
                "video_id": v,
                "subtitles": subtitles,
                "player_options": player_options,
                "not_found": True,
                "fallback_image_url": settings.FALLBACK_PLACEHOLDER_URL,
                "sprites_vtt_url": None,
                "caption_vtt": caption_vtt,
                "caption_lang": caption_lang,
            }
            return templates.TemplateResponse("embed.html", context, headers={"Cache-Control": "no-store"})

        user_uid: Optional[str] = user["user_uid"] if user else None
        await add_view(conn, video_id=v, user_uid=user_uid, duration_sec=0)
        await increment_video_views_counter(conn, video_id=v)

        # Build web URL for video via abs path
        video_src = build_storage_url(video["storage_path"].strip("/").rstrip("/") + "/original.webm")
        poster_url = build_storage_url(video["thumb_asset_path"]) if video.get("thumb_asset_path") else None

        subtitles: List[Dict[str, Any]] = []
        player_options: Dict[str, Any] = {
            "autoplay": bool(autoplay),
            "muted": bool(muted),
            "loop": bool(loop),
            "start": max(0, int(t or 0)),
        }

        sprites_vtt_rel = await get_thumbs_vtt_asset(conn, video["video_id"])
        sprites_vtt_url = build_storage_url(sprites_vtt_rel) if sprites_vtt_rel else None

        context = {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "video": video,
            "player_name": settings.VIDEO_PLAYER,
            "video_src": video_src,
            "poster_url": poster_url,
            "video_id": video["video_id"],
            "subtitles": subtitles,
            "player_options": player_options,
            "sprites_vtt_url": sprites_vtt_url,
            "caption_vtt": caption_vtt,
            "caption_lang": caption_lang,
        }
        return templates.TemplateResponse("embed.html", context, headers={"Cache-Control": "no-store"})
    finally:
        await release_conn(conn)