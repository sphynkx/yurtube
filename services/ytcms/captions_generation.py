import os
import json
import asyncio
from typing import Tuple, Dict

from services.ytcms.ytcms_client_srv import submit_and_wait

async def generate_captions(
    video_id: str,
    storage_rel: str,
    src_path: str,
    lang: str = "auto",
) -> Tuple[str, Dict]:
    loop = asyncio.get_running_loop()

    # Run blocking gRPC client in executor
    result = await loop.run_in_executor(
        None,
        lambda: submit_and_wait(
            video_path=src_path,
            video_id=video_id,
            lang=lang,
            task="transcribe",
            poll_interval=1.5,
        )
    )

    # Prepare paths
    root = os.getenv("STORAGE_ROOT", "/var/www/storage")
    base_abs = os.path.join(root, storage_rel)
    captions_dir = os.path.join(base_abs, "captions")
    os.makedirs(captions_dir, exist_ok=True)

    vtt_abs = os.path.join(captions_dir, "captions.vtt")
    meta_abs = os.path.join(captions_dir, "captions.meta.json")

    # Save VTT
    with open(vtt_abs, "w", encoding="utf-8") as f:
        vtt = result.vtt or ""
        f.write(vtt if vtt.endswith("\n") else (vtt + "\n"))

    # Meta
    meta: Dict = {
        "video_id": video_id,
        "lang": getattr(result, "detected_lang", None) or lang,
        "model": getattr(result, "model", None),
        "device": getattr(result, "device", None),
        "compute_type": getattr(result, "compute_type", None),
        "duration_sec": getattr(result, "duration_sec", None),
        "task": getattr(result, "task", "transcribe"),
    }

    with open(meta_abs, "w", encoding="utf-8") as mf:
        json.dump(meta, mf)

    rel_vtt = os.path.join(storage_rel, "captions", "captions.vtt")
    return rel_vtt, meta