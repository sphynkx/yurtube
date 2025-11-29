import os
import re
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, Response

from config.config import settings
from config.ytms_config import STORAGE_FS_ROOT
from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_owned_video

router = APIRouter(tags=["webvtt"])

_VTT_NAME_RE = re.compile(r'^[A-Za-z0-9_\-./]+\.vtt$')


def _storage_root() -> str:
    root = getattr(settings, "STORAGE_ROOT", None)
    if not root:
        root = STORAGE_FS_ROOT
    return root.rstrip("/")


def _safe_join_storage(*parts: str) -> str:
    root = os.path.normpath(_storage_root())
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


@router.get("/manage/video/{video_id}/vtt/edit")
async def webvtt_edit(request: Request, video_id: str, rel_vtt: str) -> HTMLResponse:
    """
    Simple WebVTT editor.
    rel_vtt is relative path from video's dir
    """
    storage_rel = await _ensure_owned_storage_rel(request, video_id)
    if not storage_rel:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    abs_path = _safe_join_storage(storage_rel, rel_vtt)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read_failed: {e}")

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        "manage/webvtt_editor.html",
        {
            "request": request,
            "video_id": video_id,
            "rel_vtt": rel_vtt,
            "content": content,
            "csrf_token": getattr(settings, "CSRF_TOKEN", ""),
        },
    )


@router.post("/manage/video/{video_id}/vtt/save")
async def webvtt_save(
    request: Request,
    video_id: str,
    rel_vtt: str = Form(...),
    content: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    storage_rel = await _ensure_owned_storage_rel(request, video_id)
    if not storage_rel:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    abs_path = _safe_join_storage(storage_rel, rel_vtt)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    if content is None:
        raise HTTPException(status_code=400, detail="empty_content")

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"write_failed: {e}")

    return RedirectResponse(
        url=f"/manage/video/{video_id}/vtt/edit?rel_vtt={rel_vtt}",
        status_code=303,
    )


@router.get("/manage/video/{video_id}/vtt/download")
async def webvtt_download(request: Request, video_id: str, rel_vtt: str):
    """
    To hide and pass real path to files. No direct access to files.
    """
    storage_rel = await _ensure_owned_storage_rel(request, video_id)
    if not storage_rel:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    abs_path = _safe_join_storage(storage_rel, rel_vtt)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    try:
        with open(abs_path, "rb") as f:
            data = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read_failed: {e}")

    headers = {
        "Content-Type": "text/vtt; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{os.path.basename(rel_vtt)}"',
    }
    return Response(content=data, headers=headers)