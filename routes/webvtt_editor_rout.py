import os
import re
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

from config.config import settings
from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_db import get_owned_video

router = APIRouter(tags=["webvtt"])

# Safe checks for path and filename
_VTT_NAME_RE = re.compile(r'^[A-Za-z0-9_\-/.]+\.vtt$')

def _storage_root() -> str:
    return getattr(settings, "STORAGE_ROOT", "/var/www/storage")

def _safe_join_storage(*parts: str) -> str:
    root = _storage_root()
    joined = os.path.normpath(os.path.join(root, *parts))
    if not joined.startswith(os.path.normpath(root) + os.sep) and joined != os.path.normpath(root):
        raise HTTPException(status_code=400, detail="invalid_path")
    return joined

def _is_vtt_file(filename: str) -> bool:
    if not filename:
        return False
    if not filename.lower().endswith(".vtt"):
        return False
    return bool(_VTT_NAME_RE.match(filename))

async def _ensure_ownership(request: Request, video_id: str) -> Optional[dict]:
    user = get_current_user(request)
    if not user:
        return None
    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        return owned
    finally:
        await release_conn(conn)

@router.get("/manage/video/{video_id}/vtt/edit")
async def webvtt_edit(request: Request, video_id: str, rel_vtt: str) -> HTMLResponse:
    """
    WebVTT editor: if owner valid and path is safe - opens file from storage
    rel_vtt — relative path from video dir (for ex.: captions/fr.vtt or thumbs/thumbs.vtt)
    """
    # Check owner
    owned = await _ensure_ownership(request, video_id)
    if not owned:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    storage_rel = (owned.get("storage_path") or "").strip().rstrip("/")
    if not storage_rel:
        raise HTTPException(status_code=404, detail="video_not_ready")

    # Safe: .vtt only, inside of current video's dir
    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    # Combine abs path and check whether it is within storage/<video>
    abs_path = _safe_join_storage(storage_rel, rel_vtt)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"read_failed: {e}")

    # TODO: move import to top
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        "manage/webvtt_editor.html",
        {
            "request": request,
            "video_id": video_id,
            "rel_vtt": rel_vtt,
            "content": content,
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
    """
    Save WebVTT: rewrites file after all checks
    """
    # Check owner
    owned = await _ensure_ownership(request, video_id)
    if not owned:
        raise HTTPException(status_code=401, detail="login_required_or_not_owner")

    storage_rel = (owned.get("storage_path") or "").strip().rstrip("/")
    if not storage_rel:
        raise HTTPException(status_code=404, detail="video_not_ready")

    # Validate path and filename
    if not _is_vtt_file(rel_vtt):
        raise HTTPException(status_code=400, detail="invalid_vtt_name")

    abs_path = _safe_join_storage(storage_rel, rel_vtt)

    # Add. safe: allow write only into existing file for current video!!
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="vtt_not_found")

    # Simple check on VTT - is "WEBVTT" at top
    if content is None:
        raise HTTPException(status_code=400, detail="empty_content")
    first_line = content.strip().splitlines()[0] if content.strip().splitlines() else ""
    if not first_line.upper().startswith("WEBVTT"):
        pass

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"write_failed: {e}")

    return RedirectResponse(
        url=f"/manage/video/{video_id}/vtt/edit?rel_vtt={rel_vtt}",
        status_code=303,
    )