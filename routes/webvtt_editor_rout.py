## SRTG_DONE
## SRTG_2MODIFY: STORAGE_
## SRTG_2MODIFY: build_storage_url(
## SRTG_2MODIFY: os.path.
## SRTG_2MODIFY: open(
## SRTG_2MODIFY: abs_
## SRTG_2MODIFY: _path
## SRTG_2MODIFY: vtt_file
import os
import re
from typing import Optional, List, Dict

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse, Response

from config.config import settings
from config.ytsprites.ytsprites_cfg import APP_STORAGE_FS_ROOT, APP_STORAGE_WEB_PREFIX
from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_owned_video
from db.assets_db import get_thumbs_vtt_asset
from utils.url_ut import build_storage_url

# --- Storage abstraction ---
from services.storage.base_srv import StorageClient

router = APIRouter(tags=["webvtt"])

_VTT_NAME_RE = re.compile(r'^[A-Za-z0-9_\-./]+\.vtt$')


def _storage_root() -> str:
    root = getattr(settings, "STORAGE_ROOT", None)
    if not root:
        root = STORAGE_FS_ROOT
    return root.rstrip("/")


def _safe_join_storage_abs(abs_root: str, *parts: str) -> str:
    """
    Safe join based on absolute root (from StorageClient.to_abs("")) to prevent path traversal.
    """
    root = os.path.normpath(abs_root.rstrip("/"))
    joined = os.path.normpath(os.path.join(root, *parts))
    if not (joined == root or joined.startswith(root + os.sep)):
        raise HTTPException(status_code=400, detail="invalid_path")
    return joined


def _is_vtt_file(filename: str) -> bool:
    if not filename:
        return False
    if not filename.lower().endswith(".vtt"):
        return False
    return bool(_VTT_NAME_RE.match(filename))


async def _ensure_owned_storage_rel(request: Request, video_id: str) -> Optional[str]:
    user = get_current_user(request)
    if not user:
        return None
    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return None
        storage_rel = (owned.get("storage_path") or "").strip().rstrip("/")
        return storage_rel or None
    finally:
        await release_conn(conn)


def _build_storage_url(rel_path: Optional[str]) -> Optional[str]:
    if not rel_path:
        return None
    rel_path = rel_path.lstrip("/")
    return APP_STORAGE_WEB_PREFIX.rstrip("/") + "/" + rel_path


@router.get("/manage/video/{video_id}/vtt/edit")
async def webvtt_edit(
    request: Request,
    video_id: str,
    rel_vtt: str,
    t: int = Query(0),
) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    storage_rel = await _ensure_owned_storage_rel(request, video_id)
    if not storage_rel:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    storage_client: StorageClient = request.app.state.storage
    abs_root = storage_client.to_abs("")  # absolute root
    vtt_abs_path = _safe_join_storage_abs(abs_root, storage_rel, rel_vtt)
    if not os.path.isfile(vtt_abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    # video src (original.webm)
    original_abs = _safe_join_storage_abs(abs_root, storage_rel, "original.webm")
    video_src_url = None
    if os.path.isfile(original_abs):
        video_src_url = _build_storage_url(os.path.join(storage_rel, "original.webm"))

    # sprites vtt for thumbnails preview (if any)
    conn = await get_conn()
    try:
        sprites_vtt_rel = await get_thumbs_vtt_asset(conn, video_id)
    finally:
        await release_conn(conn)
    sprites_vtt_url = build_storage_url(sprites_vtt_rel) if sprites_vtt_rel else None

    # current captions track for player
    subtitles: List[Dict[str, str]] = []
    if rel_vtt:
        base = os.path.basename(rel_vtt)
        lang_guess = "auto"
        name_no_ext = base.rsplit(".", 1)[0]
        parts = name_no_ext.split("_")
        if parts and len(parts[-1]) in (2, 3):
            lang_guess = parts[-1]
        subtitles.append({
            "label": "Captions",
            "lang": lang_guess,
            "src": f"/manage/video/{video_id}/vtt/download?rel_vtt={rel_vtt}",
            "default": True,
        })

    # options: rely on player’s own resume mechanism; start=t is optional
    player_options = {"autoplay": False, "muted": False, "loop": False, "start": max(0, int(t or 0))}

    try:
        with open(vtt_abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read_failed: {e}")

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        "manage/webvtt_editor.html",
        {
            "request": request,
            "current_user": user,
            "video_id": video_id,
            "rel_vtt": rel_vtt,
            "content": content,
            "video_src_url": video_src_url,
            "subtitles": subtitles,
            "sprites_vtt_url": sprites_vtt_url,
            "player_options": player_options,
            "csrf_token": getattr(settings, "CSRF_TOKEN", ""),
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "player_name": settings.VIDEO_PLAYER,
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
        },
    )


@router.post("/manage/video/{video_id}/vtt/save")
async def webvtt_save(
    request: Request,
    video_id: str,
    rel_vtt: str = Form(...),
    content: str = Form(...),
    t: Optional[int] = Form(None),
    csrf_token: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    storage_rel = await _ensure_owned_storage_rel(request, video_id)
    if not storage_rel:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    storage_client: StorageClient = request.app.state.storage
    abs_root = storage_client.to_abs("")  # absolute root
    vtt_abs_path = _safe_join_storage_abs(abs_root, storage_rel, rel_vtt)
    if not os.path.isfile(vtt_abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    if content is None:
        raise HTTPException(status_code=400, detail="empty_content")

    try:
        with open(vtt_abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"write_failed: {e}")

    suffix = f"&t={int(t)}" if t is not None else ""
    return RedirectResponse(
        url=f"/manage/video/{video_id}/vtt/edit?rel_vtt={rel_vtt}{suffix}",
        status_code=303,
    )


@router.get("/manage/video/{video_id}/vtt/download")
async def webvtt_download(request: Request, video_id: str, rel_vtt: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    storage_rel = await _ensure_owned_storage_rel(request, video_id)
    if not storage_rel:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    storage_client: StorageClient = request.app.state.storage
    abs_root = storage_client.to_abs("")  # absolute root
    vtt_abs_path = _safe_join_storage_abs(abs_root, storage_rel, rel_vtt)
    if not os.path.isfile(vtt_abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    try:
        with open(vtt_abs_path, "rb") as f:
            data = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read_failed: {e}")

    headers = {
        "Content-Type": "text/vtt; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{os.path.basename(rel_vtt)}"',
    }
    return Response(content=data, headers=headers)