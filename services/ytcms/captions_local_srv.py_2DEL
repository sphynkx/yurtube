import os
import json
import asyncio
from typing import Tuple, Dict

# VERY SIMPLE mock: generates a minimal VTT with 3 segments.
# Will replaced with actual whisper integration in external ytcms service.

async def generate_local_captions(
    video_id: str,
    storage_rel: str,
    src_path: str,
    lang: str = "auto",
) -> Tuple[str, Dict]:
    await asyncio.sleep(0.1)

    # Target paths
    root = os.getenv("STORAGE_ROOT", "/var/www/storage")
    base_abs = os.path.join(root, storage_rel)
    captions_dir = os.path.join(base_abs, "captions")
    os.makedirs(captions_dir, exist_ok=True)

    vtt_abs = os.path.join(captions_dir, "captions.vtt")
    meta_abs = os.path.join(captions_dir, "captions.meta.json")

    # Dummy content
    vtt_content = """WEBVTT

00:00:00.000 --> 00:00:02.000
[Caption] Video ID: %s

00:00:02.000 --> 00:00:05.000
This is a placeholder caption line.

00:00:05.000 --> 00:00:08.000
Replace with real Whisper output later.
""" % video_id

    with open(vtt_abs, "w", encoding="utf-8") as f:
        f.write(vtt_content.strip() + "\n")

    meta = {
        "video_id": video_id,
        "lang": lang,
        "model": "mock-local",
        "segments": 3,
        "duration_captured": 8.0,
        "note": "Replace this mock with external ytcms Whisper job."
    }
    with open(meta_abs, "w", encoding="utf-8") as mf:
        json.dump(meta, mf)

    rel_vtt = os.path.join(storage_rel, "captions", "captions.vtt")
    return rel_vtt, meta