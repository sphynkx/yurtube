import os
import subprocess
from shutil import which
from typing import List, Optional


def _have(cmd: str) -> bool:
    return which(cmd) is not None


def generate_default_thumbnail(input_path: str, thumbs_dir: str) -> Optional[str]:
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


def pick_thumbnail_offsets(duration_sec: Optional[int]) -> List[int]:
    if duration_sec is None or duration_sec <= 3:
        return [1]
    dur = max(1, duration_sec)
    offsets = set()
    first = min(10, max(2, int(dur * 0.05)))
    offsets.add(first)
    for frac in (0.25, 0.5, 0.75):
        t = int(dur * frac)
        if t <= 1:
            t = 2
        if t >= dur:
            t = dur - 1
        offsets.add(t)
    res = sorted(x for x in offsets if 1 <= x < dur)
    if not res:
        res = [min(5, dur - 1)]
    return res[:6]


def generate_thumbnails(input_path: str, thumbs_dir: str, offsets_sec: List[int]) -> List[str]:
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
    """
    Downscale image to fit within max_size_px, preserve aspect ratio.
    Save as PNG/JPEG depending on out_path extension.
    """
    if not _have("ffmpeg"):
        return False
    if not os.path.exists(input_path):
        return False

    # Scale longest side to max_size_px, keep AR
    # scale=iw:ih -> use conditional to cap longest side
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