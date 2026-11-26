import json
import time
import asyncio
from typing import Optional, Any, Dict

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from google.protobuf import json_format

from config.config import settings
from config.ytcms.ytcms_cfg import YTCMS_DIARIZE_DEFAULT
from db import get_conn, release_conn
from db.videos_db import get_owned_video
from db.ytsprites.ytsprites_db import fetch_video_storage_path
from db.ytcms.captions_db import set_video_captions, reset_video_captions, get_video_captions_status
from utils.security_ut import get_current_user

from services.ytcms.ytcms_client_srv import (
    submit_storage_job,
    submit_label_job,
    get_status as ytcms_get_status,
    get_result as ytcms_get_result,
    delete_captions as ytcms_delete_captions,
)
from services.ytcms.ytcms_proto import ytcms_pb2

router = APIRouter(tags=["captions"])

AUTO_MIN_DURATION = getattr(settings, "AUTO_CAPTIONS_MIN_DURATION", 3)

_JOB_STATE: Dict[str, Dict[str, Any]] = {}
_JOB_TTL_SEC = 6 * 3600

PERCENT_ACTIVE_GRACE_SEC = 12.0
PREV_STATUS_GRACE_SEC = 12.0


def _set_job_state(video_id: str, status: str, percent: int = -1, job_id: Optional[str] = None, job_server: Optional[str] = None) -> None:
    now = time.time()
    prev = _JOB_STATE.get(video_id) or {}
    _JOB_STATE[video_id] = {
        "status": status,
        "percent": int(percent if isinstance(percent, (int, float)) else -1),
        "job_id": job_id if job_id is not None else prev.get("job_id"),
        "job_server": job_server if job_server is not None else prev.get("job_server"),
        "ts": now,
        "last_active_percent": int(percent)
        if isinstance(percent, (int, float)) and 0 < int(percent) < 100
        else (prev.get("last_active_percent", -1)),
        "last_active_percent_ts": now
        if isinstance(percent, (int, float)) and 0 < int(percent) < 100
        else (prev.get("last_active_percent_ts", 0.0)),
        "last_process_status": status if status in ("start", "wait", "process") else (prev.get("last_process_status", None)),
        "last_process_status_ts": now if status in ("start", "wait", "process") else (prev.get("last_process_status_ts", 0.0)),
    }


def _get_job_state(video_id: str) -> Optional[Dict[str, Any]]:
    row = _JOB_STATE.get(video_id)
    if not row:
        return None
    if time.time() - float(row.get("ts", 0)) > _JOB_TTL_SEC:
        try:
            del _JOB_STATE[video_id]
        except Exception:
            pass
        return None
    return row


def _parse_num_speakers(raw: Optional[str]) -> Optional[int]:
    try:
        n = int(str(raw or "").strip())
    except Exception:
        return None
    return n if 1 <= n <= 8 else None


def _want_diarize(diarize: Optional[str], diarize_form: Optional[str]) -> bool:
    """
    HTML checkboxes send nothing when unchecked, so the forms also send a hidden "diarize_form" marker.
    No marker (old form, API client) -> project default.
    """
    if diarize_form:
        return str(diarize or "").strip().lower() in ("1", "true", "on", "yes")
    return bool(YTCMS_DIARIZE_DEFAULT)


def _clear_job_state(video_id: str) -> None:
    try:
        del _JOB_STATE[video_id]
    except Exception:
        pass


@router.post("/manage/video/{video_id}/captions/process")
async def captions_process(
    request: Request,
    video_id: str,
    lang: str = Form("auto"),
    diarize: Optional[str] = Form(None),
    diarize_form: Optional[str] = Form(None),
    num_speakers: Optional[str] = Form(None),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

        storage_rel = (owned.get("storage_path") or "").strip().rstrip("/")
        if not storage_rel:
            return JSONResponse({"ok": False, "error": "storage_missing"}, status_code=404)

        await reset_video_captions(conn, video_id)
        _clear_job_state(video_id)
    finally:
        await release_conn(conn)

    try:
        job_id, job_server = await asyncio.to_thread(
            submit_storage_job,
            video_id=video_id,
            storage_rel=storage_rel,
            lang=lang,
            task="transcribe",
            diarize=_want_diarize(diarize, diarize_form),
            num_speakers=_parse_num_speakers(num_speakers),
        )
        _set_job_state(video_id, status="wait", percent=-1, job_id=job_id, job_server=job_server)
    except Exception as e:
        print(f"[YTCMS] submit failed video_id={video_id}: {e}")
        _set_job_state(video_id, status="fail", percent=-1, job_id=None, job_server=None)

    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


@router.get("/internal/ytcms/captions/status")
async def captions_status(video_id: str = Query(...)):
    conn = await get_conn()
    try:
        row = await get_video_captions_status(conn, video_id)
    finally:
        await release_conn(conn)

    rel_vtt = None
    lang = None
    ready = False
    meta = None

    if row:
        rel_vtt = row.get("captions_vtt")
        lang = row.get("captions_lang")
        ready = bool(row.get("captions_ready"))
        meta_raw = row.get("captions_meta")
        if isinstance(meta_raw, dict):
            meta = meta_raw
        else:
            try:
                meta = json.loads(meta_raw) if meta_raw else None
            except Exception:
                meta = None

    job_id = None
    job_server = None
    if isinstance(meta, dict):
        job_id = meta.get("ytcms_job_id") or meta.get("job_id")
        job_server = meta.get("ytcms_job_server") or meta.get("job_server")

    js = _get_job_state(video_id) or {}
    job_id = job_id or js.get("job_id")
    job_server = job_server or js.get("job_server")

    if ready or rel_vtt:
        return {
            "ok": True,
            "video_id": video_id,
            "status": "done",
            "percent": 100,
            "has_vtt": True,
            "rel_vtt": rel_vtt,
            "lang": lang,
            "job_id": job_id,
            "job_server": job_server,
        }

    if job_id and job_server:
        try:
            st = await asyncio.to_thread(ytcms_get_status, job_id=job_id, server_addr=job_server)
            st_name = st.State.Name(st.state).lower()
            pct = int(st.percent) if isinstance(getattr(st, "percent", None), (int, float)) else -1
            pct = max(-1, min(100, pct))

            if st_name in ("queued",):
                ui_status = "wait"
            elif st_name in ("running",):
                ui_status = "process"
            elif st_name in ("done",):
                res = await asyncio.to_thread(ytcms_get_result, job_id=job_id, server_addr=job_server)
                if res.state == ytcms_pb2.JobStatus.DONE:
                    c = await get_conn()
                    try:
                        meta_to_store = {
                            "ytcms_job_id": job_id,
                            "ytcms_job_server": job_server,
                            "lang": res.detected_lang or lang,
                            "task": res.task,
                            "model": res.model,
                            "device": res.device,
                            "compute_type": res.compute_type,
                            "duration_sec": float(res.duration_sec or 0.0),
                            "vtt_rel_path": res.vtt_rel_path,
                            "meta_rel_path": res.meta_rel_path,
                        }
                        try:
                            rmeta = json_format.MessageToDict(res.meta) if res.HasField("meta") else {}
                            if rmeta:
                                meta_to_store["diarized"] = bool(rmeta.get("diarized"))
                                meta_to_store["speakers"] = int(float(rmeta.get("speakers") or 0))
                                if rmeta.get("diarize_error"):
                                    meta_to_store["diarize_error"] = str(rmeta.get("diarize_error"))
                        except Exception:
                            pass
                        await set_video_captions(c, video_id, res.vtt_rel_path, res.detected_lang or lang, meta_to_store)
                    finally:
                        await release_conn(c)

                    return {
                        "ok": True,
                        "video_id": video_id,
                        "status": "done",
                        "percent": 100,
                        "has_vtt": True,
                        "rel_vtt": res.vtt_rel_path,
                        "lang": res.detected_lang or lang,
                        "job_id": job_id,
                        "job_server": job_server,
                    }

                ui_status = "fail"
                pct = -1
            elif st_name in ("failed", "canceled"):
                ui_status = "fail"
            else:
                ui_status = "wait"

            _set_job_state(video_id, status=ui_status, percent=pct, job_id=job_id, job_server=job_server)

            return {
                "ok": True,
                "video_id": video_id,
                "status": ui_status,
                "percent": pct,
                "has_vtt": False,
                "rel_vtt": None,
                "lang": lang,
                "job_id": job_id,
                "job_server": job_server,
            }
        except Exception:
            pass

    js2 = _get_job_state(video_id)
    if js2:
        return {
            "ok": True,
            "video_id": video_id,
            "status": js2.get("status") or "wait",
            "percent": int(js2.get("percent", -1) or -1),
            "has_vtt": False,
            "rel_vtt": None,
            "lang": lang,
            "job_id": js2.get("job_id"),
            "job_server": js2.get("job_server"),
        }

    return {
        "ok": True,
        "video_id": video_id,
        "status": "idle",
        "percent": -1,
        "has_vtt": False,
        "rel_vtt": None,
        "lang": lang,
        "job_id": job_id,
        "job_server": job_server,
    }


@router.post("/internal/ytcms/captions/retry")
async def captions_retry(
    request: Request,
    video_id: str = Form(...),
    lang: str = Form("auto"),
    diarize: Optional[str] = Form(None),
    diarize_form: Optional[str] = Form(None),
    num_speakers: Optional[str] = Form(None),
    csrf_token: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login_required")

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="not_found")

        storage_rel = (owned.get("storage_path") or "").strip().rstrip("/")
        if not storage_rel:
            raise HTTPException(status_code=404, detail="storage_missing")

        await reset_video_captions(conn, video_id)
        _clear_job_state(video_id)
    finally:
        await release_conn(conn)

    try:
        job_id, job_server = await asyncio.to_thread(
            submit_storage_job,
            video_id=video_id,
            storage_rel=storage_rel,
            lang=lang,
            task="transcribe",
            diarize=_want_diarize(diarize, diarize_form),
            num_speakers=_parse_num_speakers(num_speakers),
        )
        _set_job_state(video_id, status="wait", percent=-1, job_id=job_id, job_server=job_server)
    except Exception as e:
        print(f"[YTCMS] retry submit failed video_id={video_id}: {e}")
        _set_job_state(video_id, status="fail", percent=-1, job_id=None, job_server=None)

    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


@router.post("/internal/ytcms/captions/delete")
async def captions_delete(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login_required")

    conn = await get_conn()
    try:
        storage_rel = await fetch_video_storage_path(conn, video_id, ensure_ready=True)
        if not storage_rel:
            raise HTTPException(status_code=404, detail="video_not_ready")

        await reset_video_captions(conn, video_id)
        _clear_job_state(video_id)
    finally:
        await release_conn(conn)

    try:
        await asyncio.to_thread(ytcms_delete_captions, storage_rel=storage_rel)
    except Exception as e:
        print(f"[YTCMS] delete failed video_id={video_id}: {e}")

    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


# ---------------------------------------------------------------------------
# Speaker colours for EXISTING captions (no Whisper; cue text is never changed)
# ---------------------------------------------------------------------------

_LABEL_JOBS: Dict[str, Dict[str, Any]] = {}


@router.post("/internal/ytcms/captions/diarize")
async def captions_diarize(
    request: Request,
    video_id: str = Form(...),
    num_speakers: Optional[str] = Form(None),
    csrf_token: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login_required")

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="not_found")
        storage_rel = (owned.get("storage_path") or "").strip().rstrip("/")
        row = await get_video_captions_status(conn, video_id)
    finally:
        await release_conn(conn)

    vtt_rel = ((row or {}).get("captions_vtt") or "").strip().lstrip("/")
    if not storage_rel or not vtt_rel:
        raise HTTPException(status_code=404, detail="captions_missing")
    if not vtt_rel.startswith(storage_rel + "/"):
        vtt_rel = f"{storage_rel}/{vtt_rel}"  # record holds a path relative to the video directory

    try:
        job_id, job_server = await asyncio.to_thread(
            submit_label_job,
            video_id=video_id,
            storage_rel=storage_rel,
            vtt_rel=vtt_rel,
            num_speakers=_parse_num_speakers(num_speakers),
        )
        _LABEL_JOBS[video_id] = {"job_id": job_id, "job_server": job_server, "ts": time.time(), "stored": False, "error": ""}
    except Exception as e:
        print(f"[YTCMS] label submit failed video_id={video_id}: {e}")
        _LABEL_JOBS[video_id] = {"job_id": None, "job_server": None, "ts": time.time(), "stored": True, "error": str(e)[:300]}

    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


@router.get("/internal/ytcms/captions/diarize/status")
async def captions_diarize_status(request: Request, video_id: str = Query(...)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)

    st = _LABEL_JOBS.get(video_id)
    if not st or time.time() - float(st.get("ts", 0)) > _JOB_TTL_SEC:
        return {"ok": True, "active": False}

    if st.get("error"):
        return {"ok": True, "active": True, "state": "failed", "percent": -1, "message": st["error"]}

    try:
        js = await asyncio.to_thread(ytcms_get_status, job_id=st["job_id"], server_addr=st["job_server"])
        name = js.State.Name(js.state).lower()
        pct = int(js.percent) if isinstance(getattr(js, "percent", None), (int, float)) else -1
    except Exception as e:
        return {"ok": True, "active": True, "state": "unknown", "percent": -1, "message": str(e)[:200]}

    if name in ("failed", "canceled"):
        return {"ok": True, "active": True, "state": "failed", "percent": -1, "message": getattr(js, "message", "") or "job failed"}

    if name != "done":
        return {"ok": True, "active": True, "state": "running" if name == "running" else "queued", "percent": pct}

    res = await asyncio.to_thread(ytcms_get_result, job_id=st["job_id"], server_addr=st["job_server"])
    info: Dict[str, Any] = {}
    try:
        info = json_format.MessageToDict(res.meta) if res.HasField("meta") else {}
    except Exception:
        info = {}
    diarized = bool(info.get("diarized"))
    speakers = int(float(info.get("speakers") or 0))

    if not st.get("stored"):
        st["stored"] = True
        c = await get_conn()
        try:
            row = await get_video_captions_status(c, video_id)
            meta_patch = {"diarized": diarized, "speakers": speakers, "diarize_error": str(info.get("diarize_error") or "")}
            # keep the captions record (path, language) as is; only the diarization info is added to the meta
            await set_video_captions(c, video_id, row.get("captions_vtt"), row.get("captions_lang"), meta_patch)
        finally:
            await release_conn(c)

    return {"ok": True, "active": True, "state": "done", "percent": 100, "diarized": diarized, "speakers": speakers,
            "message": "" if diarized else "fewer than two speakers found - captions left without colours"}
