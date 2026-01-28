from fastapi import APIRouter, UploadFile, File
from typing import Any, Dict
import tempfile
import asyncio
from utils.ffmpeg import probe_ffprobe_json
from utils.ytconvert.variants_ut import compute_suggested_variants

router = APIRouter()


@router.post("/internal/ytconvert/probe")
async def ytconvert_probe(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Process a file sample and return conversion format suggestions.
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

            print("[DEBUG] FFprobe raw result:", probe_result)
            suggested_variants = compute_suggested_variants(probe_result)
            print("[DEBUG]: Suggested variants:", suggested_variants)

            return {"ok": True, "suggested_variants": suggested_variants}
        finally:
            if temp_path:
                os.remove(temp_path)

    except Exception as e:
        print("[ERROR]: Exception during probe:", e)
        return {"ok": False, "error": str(e)}