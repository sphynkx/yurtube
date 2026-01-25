from __future__ import annotations

import json
from typing import List

async def create_ytconvert_job(conn, *, video_id: str, author_uid: str, requested_variants: List[str]) -> str:
    job_id = f"{video_id}-0"

    q = """
    INSERT INTO ytconvert_jobs (job_id, video_id, author_uid, state, requested_variants)
    VALUES ($1, $2, $3, 'REQUESTED', $4::jsonb)
    ON CONFLICT (job_id) DO UPDATE
      SET requested_variants = EXCLUDED.requested_variants,
          state = EXCLUDED.state,
          updated_at = NOW()
    """
    await conn.execute(q, job_id, video_id, author_uid, json.dumps(requested_variants))
    return job_id