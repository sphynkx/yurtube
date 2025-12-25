from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from config.config import settings
from db import get_conn, release_conn
from db.playlists_db import (
    add_video_to_watch_later,
    add_video_to_favorites,
    add_video_to_playlist,
    create_user_playlist,
    list_user_playlists_min,
)
from utils.security_ut import get_current_user

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _get_csrf_cookie(request: Request) -> str:
    name = getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")
    return (request.cookies.get(name) or "").strip()


def _validate_csrf(request: Request) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    if cookie_tok and (header_tok or qs_tok):
        import secrets as _sec
        form_tok = header_tok or qs_tok
        try:
            return _sec.compare_digest(cookie_tok, form_tok)
        except Exception:
            return False
    return False


@router.post("/watch_later")
async def api_watch_later(request: Request) -> Any:
    """
    JSON body: { "video_id": "XXXXXXXXXXXX" }
    Requires logged-in user and CSRF header "X-CSRF-Token": <cookie_value>.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    video_id = (body.get("video_id") or "").strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        ok = await add_video_to_watch_later(conn, user["user_uid"], video_id)
        return JSONResponse({"ok": bool(ok)})
    finally:
        await release_conn(conn)


@router.post("/favorites")
async def api_favorites(request: Request) -> Any:
    """
    JSON body: { "video_id": "XXXXXXXXXXXX" }
    Requires logged-in user and CSRF header "X-CSRF-Token": <cookie_value>.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    video_id = (body.get("video_id") or "").strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        ok = await add_video_to_favorites(conn, user["user_uid"], video_id)
        return JSONResponse({"ok": bool(ok)})
    finally:
        await release_conn(conn)


@router.post("/add")
async def api_add_to_playlist(request: Request) -> Any:
    """
    JSON body: { "playlist_id": "XXXXXXXXXXXX", "video_id": "XXXXXXXXXXXX" }
    Owner must match current user.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    playlist_id = (body.get("playlist_id") or "").strip()
    video_id = (body.get("video_id") or "").strip()
    if not playlist_id or not video_id:
        raise HTTPException(status_code=400, detail="playlist_id_and_video_id_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        # Ensure ownership
        row = await conn.fetchrow(
            "SELECT owner_uid FROM playlists WHERE playlist_id = $1",
            playlist_id,
        )
        if not row or (row["owner_uid"] != user["user_uid"]):
            raise HTTPException(status_code=403, detail="not_owner")

        ok = await add_video_to_playlist(conn, playlist_id, video_id)
        return JSONResponse({"ok": bool(ok)})
    finally:
        await release_conn(conn)


@router.post("/create")
async def api_create_playlist(request: Request) -> Any:
    """
    JSON body: { "name": "My playlist", "visibility": "private|unlisted|public" }
    Returns: { "playlist_id": "XXXXXXXXXXXX" }
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    name = (body.get("name") or "").strip()
    visibility = (body.get("visibility") or "private").strip().lower()

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        plid = await create_user_playlist(conn, user["user_uid"], name, visibility)
        return JSONResponse({"playlist_id": plid})
    finally:
        await release_conn(conn)


@router.get("/my")
async def api_my_playlists(request: Request) -> Any:
    """
    Return minimal list of current user's playlists (for future UI binding).
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    conn = await get_conn()
    try:
        rows = await list_user_playlists_min(conn, user["user_uid"], limit=200)
        return JSONResponse({"items": rows})
    finally:
        await release_conn(conn)