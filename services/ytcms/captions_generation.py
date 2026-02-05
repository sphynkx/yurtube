import os
import json
import asyncio
from typing import Tuple, Dict, Optional, Callable

from services.ytcms.ytcms_client_srv import submit_storage_job_and_wait


async def generate_captions_storage_driven(
    *,
    video_id: str,
    storage_rel: str,
    lang: str = "auto",
    task: str = "transcribe",
    on_status: Optional[Callable[[str, str, str, int, float], None]] = None,
) -> Tuple[str, Dict]:
    """
    Storage-driven captions generation:
    - SubmitJob with source=storage_rel/original.webm
    - Service writes outputs into {storage_rel}/captions/
    Returns (vtt_rel_path, meta_dict)
    """
    loop = asyncio.get_running_loop()

    source_rel = os.path.join(storage_rel, "original.webm").replace("\\", "/").lstrip("/")
    out_base = os.path.join(storage_rel, "captions").replace("\\", "/").lstrip("/")

    def _on_status_bridge(video_id2: str, job_id: str, state: str, percent: int) -> None:
        if on_status:
            # keep old signature: (video_id, job_id, status, percent, progress)
            # progress isn't available from new API (percent is).
            on_status(video_id2, job_id, state, int(percent), float(percent) / 100.0 if percent >= 0 else -1.0)

    res, job_server = await loop.run_in_executor(
        None,
        lambda: submit_storage_job_and_wait(
            video_id=video_id,
            source_rel_path=source_rel,
            output_base_rel_dir=out_base,
            lang=lang,
            task=task,
            on_status=_on_status_bridge,
        ),
    )

    if res.state != res.DONE:
        msg = res.message or (res.error.message if res.error else "") or "ytcms failed"
        raise RuntimeError(msg)

    vtt_rel = (res.vtt_rel_path or "").lstrip("/")
    meta_rel = (res.meta_rel_path or "").lstrip("/")

    meta: Dict = {
        "video_id": video_id,
        "lang": res.detected_lang or lang,
        "model": res.model or None,
        "device": res.device or None,
        "compute_type": res.compute_type or None,
        "duration_sec": float(res.duration_sec or 0.0),
        "task": res.task or task,
        "job_server": job_server,
        "job_id": None,  # optional: service could include it in meta; keep for compatibility
        "vtt_rel_path": vtt_rel,
        "meta_rel_path": meta_rel,
        "source": "ytcms",
    }

    return vtt_rel, meta