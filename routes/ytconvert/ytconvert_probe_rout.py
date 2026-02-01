from fastapi import APIRouter, UploadFile, File, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional
import tempfile
import os
import asyncio

from utils.ffmpeg import probe_ffprobe_json
from utils.ytconvert.variants_ut import compute_suggested_variants, variants_for_ui

from db import get_conn, release_conn
from utils.security_ut import get_current_user
from db.videos_query_db import get_owned_video_full as db_get_owned_video_full
from db.ytconvert.ytconvert_jobs_db import get_ytconvert_job_by_video_id


router = APIRouter()


@router.post("/internal/ytconvert/probe")
async def ytconvert_probe(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Process a file sample and return conversion format suggestions.

    UI contract:
      - video options: show only resolutions (no container/codec names)
      - audio options: only mp3, ogg
      - backend will add WEBM variants automatically on submit (server side),
        so UI should not show webm.
    """
    try:
        max_bytes = 16 * 1024 * 1024
        data = await file.read(max_bytes + 1)

        if len(data) > max_bytes:
            print("[ERROR]: Uploaded file exceeds maximum size.")
            return {"ok": False, "error": "file_too_large"}

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                temp_path = temp_file.name
                temp_file.write(data)

            print(f"[DEBUG]: Running ffprobe on temp file: {temp_path}")

            loop = asyncio.get_running_loop()
            probe_result = await loop.run_in_executor(None, lambda: probe_ffprobe_json(temp_path))

            print("[DEBUG]: FFprobe raw result:", probe_result)

            # Full backend plan (includes both mp4+webm for each height, plus audio)
            all_variants = compute_suggested_variants(probe_result)
            print("[DEBUG]: All computed variants:", all_variants)

            # What UI should display (no webm, clean labels)
            ui_variants = variants_for_ui(all_variants)
            print("[DEBUG]: UI variants for display:", ui_variants)

            return {"ok": True, "suggested_variants": ui_variants}
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    except Exception as e:
        print("[ERROR]: Exception during probe:", e)
        return {"ok": False, "error": str(e)}


@router.get("/internal/ytconvert/job-status")
async def ytconvert_job_status(request: Request, video_id: str) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        return {"ok": False, "error": "auth_required"}

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        job = await get_ytconvert_job_by_video_id(conn, video_id=video_id)
    finally:
        await release_conn(conn)

    return {"ok": True, "job": job}