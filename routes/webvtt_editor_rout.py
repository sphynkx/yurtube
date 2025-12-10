import os
import re
from typing import Optional, List, Dict

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse, Response

from config.config import settings
from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_owned_video
from db.assets_db import get_thumbs_vtt_asset
from utils.url_ut import build_storage_url

# --- Storage abstraction ---
from services.storage.base_srv import StorageClient

router = APIRouter(tags=["webvtt"])

_VTT_NAME_RE = re.compile(r'^[A-Za-z0-9_\-./]+\.vtt$')


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


def _safe_join_rel(storage_rel: str, rel_path: str) -> str:
    """
    Safely generates a relative path within storage_rel (without escaping above).
    Returns the normalized relative path "<storage_rel>/<...>".
    """
    base = storage_rel.strip().strip("/")

    # Normaloize rel path
    p = (rel_path or "").strip()
    p = p.lstrip("/")  # permit abs
    joined = os.path.normpath(os.path.join(base, p))

    base_norm = os.path.normpath(base)
    if not (joined == base_norm or joined.startswith(base_norm + os.sep)):
        raise HTTPException(status_code=400, detail="invalid_path")

    return joined


async def _storage_read_text(storage: StorageClient, rel: str, encoding: str = "utf-8") -> str:
    """
    Reads text file from storage (local/remote).
    """
    reader_ctx = storage.open_reader(rel)
    if hasattr(reader_ctx, "__await__"):
        reader_ctx = await reader_ctx

    # Try to get whole file
    data = bytearray()
    try:
        if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
            async for chunk in reader_ctx:
                if chunk:
                    data.extend(chunk)
        else:
            for chunk in reader_ctx:
                if chunk:
                    data.extend(chunk)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="vtt_not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read_failed: {e}")

    try:
        return data.decode(encoding, errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"decode_failed: {e}")


async def _storage_read_bytes(storage: StorageClient, rel: str) -> bytes:
    reader_ctx = storage.open_reader(rel)
    if hasattr(reader_ctx, "__await__"):
        reader_ctx = await reader_ctx

    buf = bytearray()
    try:
        if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
            async for chunk in reader_ctx:
                if chunk:
                    buf.extend(chunk)
        else:
            for chunk in reader_ctx:
                if chunk:
                    buf.extend(chunk)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="vtt_not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read_failed: {e}")

    return bytes(buf)


async def _storage_write_text(storage: StorageClient, rel: str, content: str, encoding: str = "utf-8") -> None:
    dir_rel = os.path.dirname(rel)
    if dir_rel:
        mkdirs_res = storage.mkdirs(dir_rel, exist_ok=True)
        if hasattr(mkdirs_res, "__await__"):
            await mkdirs_res

    w = storage.open_writer(rel, overwrite=True)
    if hasattr(w, "__await__"):
        w = await w

    data = content.encode(encoding)

    if hasattr(w, "__aenter__"):
        async with w as f:
            wr = f.write(data)
            if hasattr(wr, "__await__"):
                await wr
    else:
        with w as f:
            f.write(data)


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

    # Safely build rel path in storage_rel
    rel_path = _safe_join_rel(storage_rel, rel_vtt)

    # Read file from storage (local/remote)
    content = await _storage_read_text(storage_client, rel_path, encoding="utf-8")

    # video src (original.webm) — give the URL w/o checking local file
    original_rel = os.path.join(storage_rel, "original.webm")
    video_src_url = build_storage_url(original_rel)

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

    player_options = {"autoplay": False, "muted": False, "loop": False, "start": max(0, int(t or 0))}

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

    if content is None:
        raise HTTPException(status_code=400, detail="empty_content")

    storage_client: StorageClient = request.app.state.storage
    rel_path = _safe_join_rel(storage_rel, rel_vtt)

    # Write via StorageClient (fix for local/remote)
    await _storage_write_text(storage_client, rel_path, content, encoding="utf-8")

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
    rel_path = _safe_join_rel(storage_rel, rel_vtt)

    data = await _storage_read_bytes(storage_client, rel_path)

    headers = {
        "Content-Type": "text/vtt; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{os.path.basename(rel_vtt)}"',
    }
    return Response(content=data, headers=headers)