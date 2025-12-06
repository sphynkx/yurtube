## SRTG_DONE - no need.
## SRTG_2MODIFY: os.path.
## SRTG_2MODIFY: os.makedirs(
## SRTG_2MODIFY: shutil
## SRTG_2MODIFY: _path
## SRTG_2MODIFY: _dir
import asyncio
import os
import subprocess
from shutil import which
from typing import List, Optional


def _have(cmd: str) -> bool:
    return which(cmd) is not None


def generate_default_thumbnail(input_path: str, thumbs_dir: str) -> Optional[str]:
    # Legacy sync helper (kept for compatibility)
    if not _have("ffmpeg"):
        return None
    if not os.path.exists(input_path):
        return None
    os.makedirs(thumbs_dir, exist_ok=True)
    out_path = os.path.join(thumbs_dir, "thumb_default.jpg")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        "1",
        "-i",
        input_path,
        "-frames:v",
        "1",
        "-vf",
        "scale=320:-1:flags=bicubic",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True)
        return out_path if os.path.exists(out_path) else None
    except subprocess.CalledProcessError:
        return None


def probe_duration_seconds(input_path: str) -> Optional[int]:
    # Legacy sync helper (kept for compatibility)
    if not _have("ffprobe"):
        return None
    if not os.path.exists(input_path):
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
        try:
            sec = float(out)
            return max(0, int(round(sec)))
        except ValueError:
            return None
    except subprocess.CalledProcessError:
        return None


def pick_thumbnail_offsets(duration_sec: Optional[int]) -> List[int]:
    if duration_sec is None or duration_sec <= 3:
        return [1]
    dur = max(1, duration_sec)
    offsets = set()
    first = min(10, max(2, int(dur * 0.05)))
    offsets.add(first)
    for frac in (0.25, 0.5, 0.75):
        t = int(dur * frac)
        t = 2 if t <= 1 else (dur - 1 if t >= dur else t)
        offsets.add(t)
    res = sorted(x for x in offsets if 1 <= x < dur)
    return res[:6] if res else [min(5, dur - 1)]


def generate_thumbnails(input_path: str, thumbs_dir: str, offsets_sec: List[int]) -> List[str]:
    # Legacy sync helper (kept for compatibility)
    if not _have("ffmpeg"):
        return []
    if not os.path.exists(input_path):
        return []
    os.makedirs(thumbs_dir, exist_ok=True)
    results: List[str] = []
    index = 1
    for off in offsets_sec:
        out_path = os.path.join(thumbs_dir, f"thumb_{index}.jpg")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(off),
            "-i",
            input_path,
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-1:flags=bicubic",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True)
            if os.path.exists(out_path):
                results.append(out_path)
        except subprocess.CalledProcessError:
            pass
        index += 1
    return results


def generate_image_thumbnail(input_path: str, out_path: str, max_size_px: int) -> bool:
    # Legacy sync helper (kept for compatibility)
    if not _have("ffmpeg"):
        return False
    if not os.path.exists(input_path):
        return False
    vf = f"scale='if(gt(iw,ih),{max_size_px},-1)':'if(gt(iw,ih),-1,{max_size_px})':flags=lanczos"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        input_path,
        "-vf",
        vf,
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True)
        return os.path.exists(out_path)
    except subprocess.CalledProcessError:
        return False


def generate_animated_preview(input_path: str, out_path: str, start_sec: int, duration_sec: int = 3, fps: int = 12) -> bool:
    # Legacy sync helper (kept for compatibility)
    if not _have("ffmpeg"):
        return False
    if not os.path.exists(input_path):
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    vf = f"fps={fps},scale=320:-1:flags=lanczos"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(max(0, start_sec)),
        "-t",
        str(max(1, duration_sec)),
        "-i",
        input_path,
        "-vf",
        vf,
        "-loop",
        "0",
        "-an",
        "-lossless",
        "0",
        "-compression_level",
        "6",
        "-quality",
        "75",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True)
        return os.path.exists(out_path)
    except subprocess.CalledProcessError:
        return False


async def _run_proc(cmd: List[str]) -> int:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, _ = await proc.communicate()
    return proc.returncode


async def async_probe_duration_seconds(input_path: str) -> Optional[int]:
    if not _have("ffprobe"):
        return None
    if not os.path.exists(input_path):
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    try:
        sec = float(out.decode("utf-8", errors="ignore").strip())
        return max(0, int(round(sec)))
    except Exception:
        return None


async def async_generate_thumbnails(input_path: str, thumbs_dir: str, offsets_sec: List[int]) -> List[str]:
    if not _have("ffmpeg"):
        return []
    if not os.path.exists(input_path):
        return []
    os.makedirs(thumbs_dir, exist_ok=True)
    results: List[str] = []
    index = 1
    for off in offsets_sec:
        out_path = os.path.join(thumbs_dir, f"thumb_{index}.jpg")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(off),
            "-i",
            input_path,
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-1:flags=bicubic",
            out_path,
        ]
        rc = await _run_proc(cmd)
        if rc == 0 and os.path.exists(out_path):
            results.append(out_path)
        index += 1
    return results


async def async_generate_animated_preview(input_path: str, out_path: str, start_sec: int, duration_sec: int = 3, fps: int = 12) -> bool:
    if not _have("ffmpeg"):
        return False
    if not os.path.exists(input_path):
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    vf = f"fps={fps},scale=320:-1:flags=lanczos"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(max(0, start_sec)),
        "-t",
        str(max(1, duration_sec)),
        "-i",
        input_path,
        "-vf",
        vf,
        "-loop",
        "0",
        "-an",
        "-lossless",
        "0",
        "-compression_level",
        "6",
        "-quality",
        "75",
        out_path,
    ]
    rc = await _run_proc(cmd)
    return rc == 0 and os.path.exists(out_path)


# ---------------------------------------------
# Audio extraction/transcoding helpers (async)
# ---------------------------------------------

async def async_extract_audio_demux(input_path: str, out_path: str) -> bool:
    """
    Extract (demux) audio stream without re-encoding.
    Uses container/codec from the source. out_path extension can be arbitrary (e.g. .bin).
    """
    if not _have("ffmpeg"):
        return False
    if not os.path.exists(input_path):
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-c:a",
        "copy",
        out_path,
    ]
    rc = await _run_proc(cmd)
    return rc == 0 and os.path.exists(out_path)


async def async_transcode_audio(
    input_path: str,
    out_path: str,
    codec: str = "mp3",
    channels: int = 1,
    sample_rate: int = 16000,
    bitrate: str = "48k",
) -> bool:
    """
    Transcode audio for ASR-friendly settings.
    codec: mp3 | opus | aac | flac | wav
    """
    if not _have("ffmpeg"):
        return False
    if not os.path.exists(input_path):
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    codec = (codec or "mp3").lower().strip()
    ca = []
    if codec == "mp3":
        ca = ["-c:a", "libmp3lame", "-b:a", str(bitrate)]
        ext_ok = out_path.endswith(".mp3")
    elif codec == "opus":
        ca = ["-c:a", "libopus", "-b:a", str(bitrate)]
        ext_ok = out_path.endswith(".opus") or out_path.endswith(".ogg") or out_path.endswith(".webm")
    elif codec == "aac":
        ca = ["-c:a", "aac", "-b:a", str(bitrate)]
        ext_ok = out_path.endswith(".m4a") or out_path.endswith(".aac") or out_path.endswith(".mp4")
    elif codec == "flac":
        ca = ["-c:a", "flac", "-compression_level", "5"]
        ext_ok = out_path.endswith(".flac")
    elif codec == "wav":
        ca = ["-c:a", "pcm_s16le"]
        ext_ok = out_path.endswith(".wav")
    else:
        # fallback
        ca = ["-c:a", "libmp3lame", "-b:a", str(bitrate)]
        ext_ok = out_path.endswith(".mp3")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-ac",
        str(max(1, int(channels))),
        "-ar",
        str(max(8000, int(sample_rate))),
        *ca,
        out_path,
    ]
    rc = await _run_proc(cmd)
    return rc == 0 and os.path.exists(out_path)