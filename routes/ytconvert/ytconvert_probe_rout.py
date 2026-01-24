from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

from utils.ytconvert.variants_ut import compute_suggested_variants

router = APIRouter(tags=["ytconvert"])


def _probe_ffprobe_json(
    abs_path: str,
    *,
    timeout_sec: float = 60.0,
    probesize_bytes: int = 10 * 1024 * 1024,
    analyzeduration_us: int = 5_000_000,
) -> Dict[str, Any]:
    """
    Run ffprobe and return parsed JSON (streams + format).

    Important for sliced content:
    - limit probing so ffprobe doesn't try to scan "too much"
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        "-probesize", str(int(probesize_bytes)),
        "-analyzeduration", str(int(analyzeduration_us)),
        abs_path,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout_sec)
    try:
        return json.loads(out.decode("utf-8", "replace") or "{}")
    except Exception:
        return {}


def _extract_basic_info(probe: Dict[str, Any]) -> Dict[str, Any]:
    width = 0
    height = 0
    vcodec = ""
    acodec = ""

    streams = probe.get("streams") or []
    if isinstance(streams, list):
        for s in streams:
            if not isinstance(s, dict):
                continue
            if (s.get("codec_type") or "") == "video":
                width = int(s.get("width") or 0)
                height = int(s.get("height") or 0)
                vcodec = str(s.get("codec_name") or "")
                break
        for s in streams:
            if not isinstance(s, dict):
                continue
            if (s.get("codec_type") or "") == "audio":
                acodec = str(s.get("codec_name") or "")
                break

    fmt = probe.get("format") or {}
    bitrate = 0
    duration_sec: Optional[float] = None

    try:
        bitrate = int(fmt.get("bit_rate") or 0)
    except Exception:
        bitrate = 0

    try:
        ds = fmt.get("duration")
        if ds is not None:
            duration_sec = float(ds)
    except Exception:
        duration_sec = None

    return {
        "width": width,
        "height": height,
        "vcodec": vcodec,
        "acodec": acodec,
        "bitrate": bitrate,
        "duration_sec": duration_sec,
    }


@router.post("/internal/ytconvert/probe")
async def ytconvert_probe(
    request: Request,
    file: UploadFile = File(...),
) -> Any:
    """
    Receives a small slice of a video and runs ffprobe on it.
    Returns suggested conversion variants (stage 0).
    """
    # Allow some wiggle room (client sends 16MB, but we allow up to 32MB)
    max_bytes = 32 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if data is None:
        data = b""
    if len(data) > max_bytes:
        return JSONResponse(
            {"ok": False, "error": "probe_too_large", "max_bytes": max_bytes},
            status_code=413,
        )

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="ytprobe_", suffix=".bin")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(data)

        loop = asyncio.get_running_loop()

        def _run() -> Dict[str, Any]:
            probe = _probe_ffprobe_json(
                tmp_path,
                timeout_sec=60.0,
                probesize_bytes=10 * 1024 * 1024,
                analyzeduration_us=5_000_000,
            )
            src = _extract_basic_info(probe)
            suggested = compute_suggested_variants(src, prefer_container="mp4", include_audio=True)
            return {"src": src, "suggested": suggested}

        res = await loop.run_in_executor(None, _run)

        return JSONResponse(
            {
                "ok": True,
                "source": res.get("src") or {},
                "suggested_variants": res.get("suggested") or [],
            }
        )
    except subprocess.TimeoutExpired:
        # Return 200 with ok=false (so UI can show message without treating it as gateway/proxy error)
        return JSONResponse({"ok": False, "error": "ffprobe_timeout"}, status_code=200)
    except subprocess.CalledProcessError as e:
        return JSONResponse({"ok": False, "error": "ffprobe_failed", "details": str(e)}, status_code=200)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{e}"}, status_code=500)
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass