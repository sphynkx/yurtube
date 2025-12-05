# Integration app with ytsprites. Replacement of ytms service. Logic is same.

import os
from typing import Any, Dict, List, Tuple, Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from db import get_conn, release_conn
from db.ytsprites.ytsprites_db import (
    fetch_video_storage_path,
    reset_thumbnails_state,
    persist_vtt_asset,
    persist_sprite_assets,
    mark_thumbnails_ready,
)
from services.ytsprites.ytsprites_client_srv import submit_and_wait
from config.ytsprites.ytsprites_cfg import (
    YTSPRITES_DEFAULT_MIME,
)
from config.ytms_cfg import (
    STORAGE_FS_ROOT,
    STORAGE_WEB_PREFIX,
)

router = APIRouter(tags=["ytsprites"])

def _to_web_path(rel_path: str) -> str:
    """
    Convert a relative path (inside STORAGE_FS_ROOT) to a web path under STORAGE_WEB_PREFIX.
    """
    rel_norm = rel_path.replace("\\", "/").lstrip("/")
    web_prefix = STORAGE_WEB_PREFIX.rstrip("/")
    return f"{web_prefix}/{rel_norm}"

@router.post("/internal/ytsprites/thumbnails/retry")
async def ytsprites_thumbnails_retry(
    request: Request,
    video_id: str = Form(...),
) -> Any:
    """
    Regenerating sprites and VTTs via ytsprites (gRPC), similar to the existing ytms route.
    Input:
    - video_id: video ID (hidden form field)
    Calculating:
    - absolute path to the video file on the application side
    - MIME (default 'video/webm', or from configuration)
    Procedure:
    - reset state and delete old sprite/VTT asset records
    - send to ytsprites and get the result (sprites as binaries + VTT text)
    - save files in application storage next to the video (in the 'sprites' subfolder)
    - write paths to the DB (video_assets) for VTTs and each sprite
    - set the thumbnails_ready flag = TRUE

    Return:
    - redirect to referrer (if any), otherwise a simple HTML page "OK".
    """
    # DB: get the relative `storage_path` from the `videos` table
    conn = await get_conn()
    try:
        rel_video_path = await fetch_video_storage_path(conn, video_id, ensure_ready=False)
        if not rel_video_path:
            # No path - return to the page unchanged
            ref = request.headers.get("referer")
            if ref:
                return RedirectResponse(ref, status_code=303)
            return HTMLResponse("<html><body><p>No storage path for video.</p></body></html>", status_code=200)

        # Abs path to the video in storage
        abs_video_path = os.path.join(STORAGE_FS_ROOT, rel_video_path.lstrip("/"))
        # Default MIMEis  webm (of from config)
        video_mime = (YTSPRITES_DEFAULT_MIME or "video/webm").strip() or "video/webm"

        # Remove old sprites/VTT
        await reset_thumbnails_state(conn, video_id)

        # Call gRPC client: get binary sprites and VTT
        # submit_and_wait: (video_id, video_abs_path, video_mime) -> (video_id, [(name, bytes)], vtt_text)
        video_id2, sprites, vtt_text = submit_and_wait(video_id, abs_video_path, video_mime)

        # Target dir for new sprites close to the video: <parent_of_rel_video_path>/sprites
        rel_dir = os.path.join(os.path.dirname(rel_video_path), "sprites")
        abs_dir = os.path.join(STORAGE_FS_ROOT, rel_dir.lstrip("/"))

        try:
            os.makedirs(abs_dir, exist_ok=True)
        except Exception:
            # If dir failed to create, an attempt will be made to continue, but writing files may fail.
            pass

        # Save VTT
        rel_vtt = os.path.join(rel_dir, "sprites.vtt")
        abs_vtt = os.path.join(STORAGE_FS_ROOT, rel_vtt.lstrip("/"))
        try:
            with open(abs_vtt, "w", encoding="utf-8") as f:
                f.write(vtt_text or "")
        except Exception:
            # Write empty (or may skip)
            try:
                with open(abs_vtt, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception:
                pass

        # Save sprites
        rel_sprite_paths: List[str] = []
        for name, data in sprites:
            # Sprites filenames comes from `ytsprites` service: sprite_0001.jpg, sprite_0002.jpg etc
            rel_sprite = os.path.join(rel_dir, name)
            abs_sprite = os.path.join(STORAGE_FS_ROOT, rel_sprite.lstrip("/"))
            try:
                with open(abs_sprite, "wb") as f:
                    f.write(data or b"")
                rel_sprite_paths.append(rel_sprite)
            except Exception:
                # If some sprite couldnt be saved, skip it
                continue

        # Write paths to DB
        await persist_vtt_asset(conn, video_id, _to_web_path(rel_vtt))
        await persist_sprite_assets(conn, video_id, [_to_web_path(p) for p in rel_sprite_paths])

        # Set ready state
        await mark_thumbnails_ready(conn, video_id)

    finally:
        await release_conn(conn)

    ref = request.headers.get("referer")
    if ref:
        return RedirectResponse(ref, status_code=303)
    return HTMLResponse("<html><body><p>OK</p></body></html>", status_code=200)