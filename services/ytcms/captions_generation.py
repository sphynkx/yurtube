from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from services.ytcms.ytcms_client_srv import submit_storage_job, poll_until_done
from services.ytcms.ytcms_proto import ytcms_pb2


async def generate_captions(
    *,
    video_id: str,
    storage_rel: str,
    src_path: str | None = None,  # kept for backward-compat signature; ignored in storage-driven flow
    lang: str = "auto",
    on_status: Optional[Callable[[str, str, str, int, float], Any]] = None,
    storage_client: Any = None,  # kept; not used
) -> Tuple[str, Dict[str, Any]]:
    """
    Backward-compatible wrapper used by old routes.

    New behavior:
    - Submit job by storage path (storage_rel/original.webm)
    - Poll until done
    - Return (vtt_rel_path, meta_dict)
    """
    job_id, job_server = submit_storage_job(video_id=video_id, storage_rel=storage_rel, lang=lang, task="transcribe")

    if on_status:
        try:
            on_status(video_id, job_id, "queued", -1, -1.0)
        except Exception:
            pass

    res = poll_until_done(job_id=job_id, server_addr=job_server)

    # Normalize result
    state_name = ytcms_pb2.JobStatus.State.Name(res.state) if hasattr(ytcms_pb2.JobStatus, "State") else str(res.state)

    meta: Dict[str, Any] = {
        "job_id": job_id,
        "job_server": job_server,
        "state": state_name,
        "lang": getattr(res, "detected_lang", "") or lang,
        "task": getattr(res, "task", "") or "transcribe",
        "model": getattr(res, "model", "") or "",
        "device": getattr(res, "device", "") or "",
        "compute_type": getattr(res, "compute_type", "") or "",
        "duration_sec": float(getattr(res, "duration_sec", 0.0) or 0.0),
        "meta_rel_path": getattr(res, "meta_rel_path", "") or "",
    }

    vtt_rel = getattr(res, "vtt_rel_path", "") or ""
    if not vtt_rel:
        raise RuntimeError(f"ytcms_result_missing_vtt: state={state_name}")

    if on_status:
        try:
            on_status(video_id, job_id, "done" if state_name == "DONE" else "fail", 100 if state_name == "DONE" else -1, 1.0)
        except Exception:
            pass

    return vtt_rel, meta