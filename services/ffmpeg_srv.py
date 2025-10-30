import os
import subprocess
from shutil import which
from typing import Optional


def _have(cmd: str) -> bool:
    return which(cmd) is not None


def generate_default_thumbnail(input_path: str, thumbs_dir: str) -> Optional[str]:
    """
    Generate a default thumbnail (JPEG) from input video at ~1s.
    Returns absolute path to the generated thumbnail (thumb_default.jpg),
    or None if ffmpeg is unavailable or generation failed.
    """
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
        if os.path.exists(out_path):
            return out_path
        return None
    except subprocess.CalledProcessError:
        return None


def probe_duration_seconds(input_path: str) -> Optional[int]:
    """
    Returns duration in whole seconds using ffprobe, or None if unavailable.
    """
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
        if not out:
            return None
        try:
            sec = float(out)
            return max(0, int(round(sec)))
        except ValueError:
            return None
    except subprocess.CalledProcessError:
        return None