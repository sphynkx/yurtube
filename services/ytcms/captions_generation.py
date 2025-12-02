import os
import json
import asyncio
from typing import Tuple, Dict, Optional, Callable

from services.ytcms.ytcms_client_srv import submit_and_wait

async def generate_captions(
    video_id: str,
    storage_rel: str,
    src_path: str,
    lang: str = "auto",
    on_status: Optional[Callable[[str, str, str, int, float], None]] = None,
) -> Tuple[str, Dict]:
    loop = asyncio.get_running_loop()

    # Run gRPC-client in executor
    result = await loop.run_in_executor(
        None,
        lambda: submit_and_wait(
            video_path=src_path,
            video_id=video_id,
            lang=lang,
            task="transcribe",
            poll_interval=1.0,   # YTCMS call.. todo: set faster
            on_status=on_status, # pass the callback to the top
        )
    )

    root = os.getenv("STORAGE_ROOT", "/var/www/storage")
    base_abs = os.path.join(root, storage_rel)
    captions_dir = os.path.join(base_abs, "captions")
    os.makedirs(captions_dir, exist_ok=True)

    vtt_abs = os.path.join(captions_dir, "captions.vtt")
    meta_abs = os.path.join(captions_dir, "captions.meta.json")

    # Store VTT (ResultReply.content or .vtt)
    vtt_payload = getattr(result, "vtt", None) or getattr(result, "content", "") or ""
    with open(vtt_abs, "w", encoding="utf-8") as f:
        f.write(vtt_payload if vtt_payload.endswith("\n") else (vtt_payload + "\n"))

    # Metadata: add percent/progress/job_id
    percent = getattr(result, "percent", -1)
    progress = getattr(result, "progress", -1.0)
    job_id = getattr(result, "job_id", None)

    meta: Dict = {
        "video_id": video_id,
        "lang": getattr(result, "detected_lang", None) or lang,
        "model": getattr(result, "model", None),
        "device": getattr(result, "device", None),
        "compute_type": getattr(result, "compute_type", None),
        "duration_sec": getattr(result, "duration_sec", None),
        "task": getattr(result, "task", "transcribe"),
        "job_id": job_id,
        "source": "ytcms",
        "percent": int(percent) if isinstance(percent, (int, float)) else -1,
        "progress": float(progress) if isinstance(progress, (int, float)) else -1.0,
    }

    with open(meta_abs, "w", encoding="utf-8") as mf:
        json.dump(meta, mf)

    rel_vtt = os.path.join(storage_rel, "captions", "captions.vtt")
    return rel_vtt, meta