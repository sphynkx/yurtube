from typing import Any, Dict
import tempfile
import os
import asyncio
import inspect

from fastapi import APIRouter, Request, HTTPException
from utils.security_ut import get_current_user
from db import get_conn, release_conn
from db.videos_query_db import get_owned_video_full as db_get_owned_video_full
from services.ytstorage.base_srv import StorageClient
from utils.ffmpeg import probe_ffprobe_json
from utils.ytconvert.variants_ut import compute_suggested_variants, variants_for_ui

router = APIRouter()

async def _read_prefix_to_temp(storage: StorageClient, rel_path: str, *, max_bytes: int, suffix: str) -> str:
    """
    Read first max_bytes from storage rel_path into a temp file.
    Works with both async and sync open_reader().
    """
    tmp = tempfile.NamedTemporaryFile(prefix="yt_probe_", suffix=suffix, delete=False)
    try:
        remaining = int(max_bytes)

        reader_ctx = storage.open_reader(rel_path)  # type: ignore
        if inspect.isawaitable(reader_ctx):
            reader_ctx = await reader_ctx

        if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
            async for chunk in reader_ctx:
                if not chunk:
                    continue
                b = bytes(chunk)
                if len(b) > remaining:
                    tmp.write(b[:remaining])
                    break
                tmp.write(b)
                remaining -= len(b)
                if remaining <= 0:
                    break
        else:
            # sync iterator or file-like
            try:
                while remaining > 0:
                    buf = reader_ctx.read(min(1024 * 1024, remaining))
                    if not buf:
                        break
                    tmp.write(buf)
                    remaining -= len(buf)
            finally:
                try:
                    reader_ctx.close()
                except Exception:
                    pass

        tmp.flush()
        return tmp.name
    finally:
        try:
            tmp.close()
        except Exception:
            pass

@router.get("/internal/ytconvert/probe-video")
async def ytconvert_probe_video(request: Request, video_id: str) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        return {"ok": False, "error": "auth_required"}

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        storage_rel = str(owned["storage_path"] or "").strip().strip("/")
        original_rel = f"{storage_rel}/original.webm"

        storage_client: StorageClient = request.app.state.storage

        # materialize prefix
        temp_path = None
        try:
            temp_path = await _read_prefix_to_temp(storage_client, original_rel, max_bytes=16 * 1024 * 1024, suffix=".webm")

            loop = asyncio.get_running_loop()
            probe_result = await loop.run_in_executor(None, lambda: probe_ffprobe_json(temp_path))

            all_variants = compute_suggested_variants(probe_result)
            ui_variants = variants_for_ui(all_variants)

            return {"ok": True, "suggested_variants": ui_variants}
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    finally:
        await release_conn(conn)