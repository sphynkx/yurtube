from typing import Any, Dict, List, Optional
import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from services.search.search_client_srch import get_backend
from services.search.settings_srch import settings
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from db import get_conn, release_conn

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _page_args(page: int, per_page: int) -> Dict[str, int]:
    p = max(1, page)
    pp = max(1, min(per_page, 50))
    return {"limit": pp, "offset": (p - 1) * pp, "page": p, "per_page": pp}


async def _enrich_results(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich rows with:
    - thumb_url (static) from video_assets (thumbnail_default)
    - thumb_url_anim from video_assets (thumbnail_anim)
    - avatar_url from user_assets (avatar)
    - uploaded_at formatted date string from videos.created_at
    - author name (db username preferred)
    """
    if not rows:
        return rows
    ids = [r.get("video_id") for r in rows if r.get("video_id")]
    ids = [i for i in ids if isinstance(i, str) and i.strip()]
    if not ids:
        return rows

    conn = await get_conn()
    try:
        q = """
        SELECT
          v.video_id,
          v.created_at,
          v.author_uid,
          u.username,
          ua.path AS avatar_asset_path,
          vthumb.path AS thumb_asset_path,
          vanim.path AS thumb_anim_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        LEFT JOIN video_assets vthumb
          ON vthumb.video_id = v.video_id AND vthumb.asset_type = 'thumbnail_default'
        LEFT JOIN video_assets vanim
          ON vanim.video_id = v.video_id AND vanim.asset_type = 'thumbnail_anim'
        WHERE v.video_id = ANY($1::text[])
        """
        rows_db = await conn.fetch(q, ids)
        by_id: Dict[str, Dict[str, Any]] = {}
        for r in rows_db:
            d = dict(r)
            by_id[d["video_id"]] = d
    finally:
        await release_conn(conn)

    out: List[Dict[str, Any]] = []
    for r in rows:
        vid = r.get("video_id")
        dbi = by_id.get(vid) if vid else None

        thumb_url: Optional[str] = None
        thumb_url_anim: Optional[str] = None
        avatar_url: Optional[str] = None
        uploaded_at: Optional[str] = None

        if dbi:
            if dbi.get("thumb_asset_path"):
                thumb_url = build_storage_url(dbi["thumb_asset_path"])
            if dbi.get("thumb_anim_asset_path"):
                thumb_url_anim = build_storage_url(dbi["thumb_anim_asset_path"])
            if dbi.get("avatar_asset_path"):
                avatar_url = build_storage_url(dbi["avatar_asset_path"])
            dt = dbi.get("created_at")
            if isinstance(dt, datetime.datetime):
                uploaded_at = dt.strftime("%Y-%m-%d")
            elif dt is not None:
                try:
                    uploaded_at = str(dt)
                except Exception:
                    uploaded_at = None

        author_name = r.get("author") or (dbi.get("username") if dbi else "")

        rr = dict(r)
        rr["thumb_url"] = thumb_url
        rr["thumb_url_anim"] = thumb_url_anim
        rr["avatar_url"] = avatar_url
        rr["uploaded_at"] = uploaded_at
        rr["author"] = author_name or ""
        out.append(rr)
    return out


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query("", min_length=0, max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=50),
) -> Any:
    args = _page_args(page, per_page)
    backend = get_backend()
    rows = await backend.search_videos(q, args["limit"], args["offset"])
    rows = await _enrich_results(rows)
    user = get_current_user(request)
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "current_user": user,
            "query": q,
            "results": rows,
            "page": args["page"],
            "per_page": args["per_page"],
            "engine": settings.BACKEND,
        },
    )


@router.get("/search/suggest")
async def search_suggest(q: str = Query("", min_length=1, max_length=200), limit: int = Query(8, ge=1, le=20)) -> Any:
    backend = get_backend()
    items = await backend.suggest_titles(q, limit)
    return JSONResponse({"items": items})