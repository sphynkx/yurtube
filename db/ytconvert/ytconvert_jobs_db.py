from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


async def create_ytconvert_job(
    conn,
    *,
    video_id: str,
    author_uid: str,
    requested_variants: List[str],
) -> str:
    """
    Create (or upsert) a local ytconvert job request row.

    MVP: one job per video: job_id = "{video_id}-0"
    Later: switch to UUID/ULID if multiple jobs per video become needed.
    """
    job_id = f"{video_id}-0"

    q = """
    INSERT INTO ytconvert_jobs (job_id, video_id, author_uid, state, requested_variants, progress_percent, message, meta)
    VALUES ($1, $2, $3, 'REQUESTED', $4::jsonb, 0, '', '{}'::jsonb)
    ON CONFLICT (job_id) DO UPDATE
      SET requested_variants = EXCLUDED.requested_variants,
          state = EXCLUDED.state,
          updated_at = NOW()
    """
    await conn.execute(q, job_id, video_id, author_uid, _json(requested_variants))
    return job_id


async def set_ytconvert_job_grpc_id(
    conn,
    job_id: str,
    *,
    grpc_job_id: str,
    state: str = "SUBMITTED",
    message: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    q = """
    UPDATE ytconvert_jobs
       SET grpc_job_id = $2,
           state = $3,
           message = $4,
           meta = COALESCE(meta, '{}'::jsonb) || $5::jsonb,
           updated_at = NOW()
     WHERE job_id = $1
    """
    await conn.execute(q, job_id, grpc_job_id, state, message or "", _json(meta or {}))


async def update_ytconvert_job_state(
    conn,
    job_id: str,
    *,
    state: str,
    progress_percent: int = 0,
    message: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    # Clamp percent defensively
    try:
        p = int(progress_percent)
    except Exception:
        p = 0
    if p < 0:
        p = 0
    if p > 100:
        p = 100

    q = """
    UPDATE ytconvert_jobs
       SET state = $2,
           progress_percent = $3,
           message = $4,
           meta = COALESCE(meta, '{}'::jsonb) || $5::jsonb,
           updated_at = NOW()
     WHERE job_id = $1
    """
    await conn.execute(q, job_id, state, p, message or "", _json(meta or {}))


async def set_ytconvert_job_done(
    conn,
    job_id: str,
    *,
    message: str = "DONE",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    q = """
    UPDATE ytconvert_jobs
       SET state = 'DONE',
           progress_percent = 100,
           message = $2,
           meta = COALESCE(meta, '{}'::jsonb) || $3::jsonb,
           updated_at = NOW()
     WHERE job_id = $1
    """
    await conn.execute(q, job_id, message or "DONE", _json(meta or {}))


async def set_ytconvert_job_failed(
    conn,
    job_id: str,
    *,
    message: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    q = """
    UPDATE ytconvert_jobs
       SET state = 'FAILED',
           message = $2,
           meta = COALESCE(meta, '{}'::jsonb) || $3::jsonb,
           updated_at = NOW()
     WHERE job_id = $1
    """
    await conn.execute(q, job_id, message or "FAILED", _json(meta or {}))