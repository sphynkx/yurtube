from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _meta_dict(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    try:
        d = dict(v)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _jsonb_param(d: Dict[str, Any]) -> str:
    # stable, always returns JSON string acceptable for $x::jsonb
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


# =========================
# New API used by ytcms routes (asyncpg)
# =========================

async def set_captions_job(
    conn,
    *,
    video_id: str,
    job_id: str,
    job_server: str,
    lang: str,
    task: str,
) -> None:
    sql = """
    UPDATE videos
       SET captions_ready = FALSE,
           captions_vtt = NULL,
           captions_lang = NULL,
           captions_meta = COALESCE(captions_meta, '{}'::jsonb) ||
                          jsonb_build_object(
                            'ytcms_job_id', $1::text,
                            'ytcms_job_server', $2::text,
                            'ytcms_lang', $3::text,
                            'ytcms_task', $4::text,
                            'ytcms_state', 'QUEUED',
                            'ytcms_percent', 0,
                            'ytcms_error', '',
                            'ytcms_updated_at', EXTRACT(EPOCH FROM NOW())
                          )
     WHERE video_id = $5::text
    """
    await conn.execute(sql, str(job_id), str(job_server), str(lang), str(task), str(video_id))


async def get_captions_job(conn, *, video_id: str) -> Dict[str, str]:
    sql = """
    SELECT
      COALESCE(captions_meta->>'ytcms_job_id', '') AS job_id,
      COALESCE(captions_meta->>'ytcms_job_server', '') AS job_server,
      COALESCE(captions_meta->>'ytcms_lang', '') AS lang,
      COALESCE(captions_meta->>'ytcms_task', '') AS task
    FROM videos
    WHERE video_id = $1
    """
    row = await conn.fetchrow(sql, str(video_id))
    if not row:
        return {"job_id": "", "job_server": "", "lang": "", "task": ""}
    return {
        "job_id": row["job_id"] or "",
        "job_server": row["job_server"] or "",
        "lang": row["lang"] or "",
        "task": row["task"] or "",
    }


async def update_captions_job_status(
    conn,
    *,
    video_id: str,
    state: str,
    percent: int,
    error: str = "",
) -> None:
    sql = """
    UPDATE videos
       SET captions_meta = COALESCE(captions_meta, '{}'::jsonb) ||
                          jsonb_build_object(
                            'ytcms_state', $1::text,
                            'ytcms_percent', $2::int,
                            'ytcms_error', $3::text,
                            'ytcms_updated_at', EXTRACT(EPOCH FROM NOW())
                          )
     WHERE video_id = $4::text
    """
    await conn.execute(sql, str(state), int(percent), str(error or ""), str(video_id))


async def finalize_captions_success(
    conn,
    *,
    video_id: str,
    vtt_rel_path: str,
    meta_rel_path: str,
    detected_lang: str,
    task: str,
    model: str,
    device: str,
    compute_type: str,
    duration_sec: float,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> None:
    base_meta: Dict[str, Any] = {
        "ytcms_state": "DONE",
        "ytcms_percent": 100,
        "ytcms_error": "",
        "ytcms_vtt_rel_path": (vtt_rel_path or "").lstrip("/"),
        "ytcms_meta_rel_path": (meta_rel_path or "").lstrip("/"),
        "ytcms_detected_lang": detected_lang or "",
        "ytcms_task": task or "",
        "ytcms_model": model or "",
        "ytcms_device": device or "",
        "ytcms_compute_type": compute_type or "",
        "ytcms_duration_sec": float(duration_sec or 0.0),
    }
    if extra_meta:
        base_meta.update(extra_meta)

    vtt_rel = (vtt_rel_path or "").lstrip("/")
    lang_val = (detected_lang or "").strip() or None
    meta_json = _jsonb_param(base_meta)

    sql = """
    UPDATE videos
       SET captions_vtt = $1::text,
           captions_lang = $2::text,
           captions_ready = TRUE,
           captions_meta = COALESCE(captions_meta, '{}'::jsonb) || $3::jsonb ||
                          jsonb_build_object('ytcms_updated_at', EXTRACT(EPOCH FROM NOW()))
     WHERE video_id = $4::text
    """
    await conn.execute(sql, vtt_rel, lang_val, meta_json, str(video_id))


async def mark_captions_failed(conn, *, video_id: str, error: str) -> None:
    sql = """
    UPDATE videos
       SET captions_ready = FALSE,
           captions_meta = COALESCE(captions_meta, '{}'::jsonb) ||
                          jsonb_build_object(
                            'ytcms_state', 'FAILED',
                            'ytcms_error', $1::text,
                            'ytcms_updated_at', EXTRACT(EPOCH FROM NOW())
                          )
     WHERE video_id = $2::text
    """
    await conn.execute(sql, str(error or "ytcms failed"), str(video_id))


async def reset_captions(conn, *, video_id: str) -> None:
    sql = """
    UPDATE videos
       SET captions_vtt = NULL,
           captions_lang = NULL,
           captions_ready = FALSE,
           captions_meta = (
             COALESCE(captions_meta, '{}'::jsonb)
             - 'ytcms_job_id'
             - 'ytcms_job_server'
             - 'ytcms_lang'
             - 'ytcms_task'
             - 'ytcms_state'
             - 'ytcms_percent'
             - 'ytcms_error'
             - 'ytcms_updated_at'
             - 'ytcms_vtt_rel_path'
             - 'ytcms_meta_rel_path'
             - 'ytcms_detected_lang'
             - 'ytcms_model'
             - 'ytcms_device'
             - 'ytcms_compute_type'
             - 'ytcms_duration_sec'
           )
     WHERE video_id = $1::text
    """
    await conn.execute(sql, str(video_id))


# =========================
# Backward-compatible API (legacy imports used elsewhere in app)
# =========================

async def set_video_captions(
    conn,
    video_id: str,
    captions_vtt: str,
    captions_lang: Optional[str] = None,
    captions_meta: Optional[Dict[str, Any]] = None,
) -> None:
    vtt_rel = (captions_vtt or "").lstrip("/")
    lang_val = (captions_lang or "").strip() or None
    meta_json = _jsonb_param(captions_meta or {})

    sql = """
    UPDATE videos
       SET captions_vtt = $1::text,
           captions_lang = $2::text,
           captions_ready = TRUE,
           captions_meta = COALESCE(captions_meta, '{}'::jsonb) || $3::jsonb
     WHERE video_id = $4::text
    """
    await conn.execute(sql, vtt_rel, lang_val, meta_json, str(video_id))


async def reset_video_captions(conn, video_id: str) -> None:
    await reset_captions(conn, video_id=str(video_id))


async def get_video_captions_status(conn, video_id: str) -> Dict[str, Any]:
    sql = """
    SELECT video_id, captions_ready, captions_vtt, captions_lang, captions_meta
    FROM videos
    WHERE video_id = $1
    """
    row = await conn.fetchrow(sql, str(video_id))
    if not row:
        return {
            "video_id": video_id,
            "captions_ready": False,
            "captions_vtt": None,
            "captions_lang": None,
            "state": "NOT_FOUND",
            "percent": 0,
            "error": "video_not_found",
        }

    meta = _meta_dict(row["captions_meta"])
    ready = bool(row["captions_ready"])

    return {
        "video_id": row["video_id"],
        "captions_ready": ready,
        "captions_vtt": row["captions_vtt"],
        "captions_lang": row["captions_lang"],
        "state": meta.get("ytcms_state") or ("DONE" if ready else "IDLE"),
        "percent": int(meta.get("ytcms_percent") or (100 if ready else 0)),
        "error": meta.get("ytcms_error") or "",
        "job_id": meta.get("ytcms_job_id") or "",
        "job_server": meta.get("ytcms_job_server") or "",
    }