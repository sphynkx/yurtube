from __future__ import annotations
import os
import inspect
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import get_owned_video
from utils.security_ut import get_current_user

# --- Storage abstraction ---
from services.ytstorage.base_srv import StorageClient

from services.yttrans.yttrans_client_srv import list_languages

router = APIRouter(tags=["yttrans"])
templates = Jinja2Templates(directory="templates")


@router.get("/manage/video/{video_id}/translations", response_class=HTMLResponse)
async def video_translations_page(request: Request, video_id: str) -> Any:
    """
    Translations management UI.
    Visible only if captions/captions.vtt exists for the video.
    Initially shows available target languages fetched from yttrans service.
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        storage_rel = owned["storage_path"].rstrip("/")

        # Check if primary captions exist
        storage_client: StorageClient = request.app.state.storage
        captions_rel = os.path.join(storage_rel, "captions", "captions.vtt")
        exists_res = storage_client.exists(captions_rel)
        if inspect.isawaitable(exists_res):
            has_captions = bool(await exists_res)
        else:
            has_captions = bool(exists_res)

        # Fetch available target languages from yttrans (if captions exist)
        langs: List[str] = []
        default_src: str = "auto"
        meta: Dict[str, Any] = {}
        if has_captions:
            try:
                langs, default_src, meta = await list_languages()
            except Exception as e:
                # Do not fail UI; show an alert in the template
                langs = []
                default_src = "auto"
                meta = {"error": f"{e}"}

        csrf_token = getattr(settings, "CSRF_TOKEN", "")
        return templates.TemplateResponse(
            "manage/video_translations.html",
            {
                "request": request,
                "current_user": user,
                "video_id": video_id,
                "has_captions": has_captions,
                "target_langs": langs,
                "default_source_lang": default_src,
                "yttrans_meta": meta,
                "csrf_token": csrf_token,
                "brand_logo_url": settings.BRAND_LOGO_URL,
                "brand_tagline": settings.BRAND_TAGLINE,
                "favicon_url": settings.FAVICON_URL,
                "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
            },
            headers={"Cache-Control": "no-store"},
        )
    finally:
        await release_conn(conn)