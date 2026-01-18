import os
import json
import time
import asyncio
import inspect
import tempfile
import shutil
from typing import Optional, Any, Dict, Tuple, Iterable

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import get_owned_video
from db.ytsprites.ytsprites_db import fetch_video_storage_path
from db.captions_db import set_video_captions, reset_video_captions, get_video_captions_status
from utils.security_ut import get_current_user
from services.ytcms.captions_generation import generate_captions
from services.ffmpeg_srv import async_probe_duration_seconds

# Storage abstraction
from services.ytstorage.base_srv import StorageClient

router = APIRouter(tags=["captions"])

AUTO_MIN_DURATION = getattr(settings, "AUTO_CAPTIONS_MIN_DURATION", 3)

_JOB_STATE: Dict[str, Dict[str, Any]] = {}
_JOB_TTL_SEC = 6 * 3600
LAST_ACTIVE_GRACE_SEC = 10.0

# Gisteresis params to endless status "blink"
PERCENT_ACTIVE_GRACE_SEC = 12.0
PREV_STATUS_GRACE_SEC = 12.0


def _set_job_state(video_id: str, status: str, percent: int = -1, job_id: Optional[str] = None) -> None:
    now = time.time()
    prev = _JOB_STATE.get(video_id) or {}
    _JOB_STATE[video_id] = {
        "status": status,
        "percent": int(percent if isinstance(percent, (int, float)) else -1),
        "job_id": job_id if job_id is not None else prev.get("job_id"),
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


def _clear_job_state(video_id: str) -> None:
    try:
        del _JOB_STATE[video_id]
    except Exception:
        pass


# Status callback for generator
def _on_status_callback(video_id: str, job_id: str, status: str, percent: int, progress: float) -> None:
    st = (status or "").strip().lower()
    if st in ("queued", "start", "wait"):
        st_norm = "wait"
    elif st in ("processing", "process"):
        st_norm = "process"
    elif st in ("done", "finished", "complete"):
        st_norm = "done"
    elif st in ("error", "fail", "failed"):
        st_norm = "fail"
    else:
        st_norm = "wait"

    p = -1
    try:
        if isinstance(percent, (int, float)) and int(percent) >= 0:
            p = int(percent)
        elif isinstance(progress, (int, float)) and float(progress) >= 0.0:
            p = max(0, min(100, int(round(float(progress) * 100))))
    except Exception:
        p = -1

    _set_job_state(video_id, status=st_norm, percent=p, job_id=job_id)


async def _ensure_local_original(storage: StorageClient, original_rel: str) -> Tuple[str, Optional[str]]:
    """
    Ensure a local path to the original asset:
    - If storage.to_abs(original_rel) exists locally -> return (abs_path, None)
    - Else download to a temporary directory and return (tmp_abs_path, tmp_dir)
    """
    original_abs_storage = storage.to_abs(original_rel)
    if os.path.exists(original_abs_storage):
        return original_abs_storage, None

    tmp_dir = tempfile.mkdtemp(prefix="ytcms_")
    tmp_original_abs = os.path.join(tmp_dir, os.path.basename(original_rel) or "original.webm")

    reader_ctx = storage.open_reader(original_rel)
    if inspect.isawaitable(reader_ctx):
        reader_ctx = await reader_ctx

    wrote_any = False
    try:
        if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
            async for chunk in reader_ctx:
                if chunk:
                    with open(tmp_original_abs, "ab") as lf:
                        lf.write(chunk)
                        wrote_any = True
        else:
            for chunk in reader_ctx:
                if chunk:
                    with open(tmp_original_abs, "ab") as lf:
                        lf.write(chunk)
                        wrote_any = True
    except Exception as e:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"download_failed: {e}")

    if not wrote_any or not os.path.exists(tmp_original_abs):
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="original_missing")

    return tmp_original_abs, tmp_dir


@router.post("/manage/video/{video_id}/captions/process")
async def captions_process(
    request: Request,
    video_id: str,
    lang: str = Form("auto"),
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
        duration = int(owned.get("duration_sec") or 0)
        storage_rel = owned["storage_path"].rstrip("/")
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    original_rel = os.path.join(storage_rel, "original.webm")

    try:
        original_abs, tmp_dir = await _ensure_local_original(storage_client, original_rel)
    except HTTPException as e:
        return JSONResponse({"ok": False, "error": e.detail}, status_code=e.status_code)

    try:
        dsec = await async_probe_duration_seconds(original_abs)
        if dsec and dsec > 0:
            duration = int(dsec)
    except Exception:
        pass

    async def _bg_worker():
        _set_job_state(video_id, status="wait", percent=-1, job_id=None)
        try:
            rel_vtt, meta = await generate_captions(
                video_id=video_id,
                storage_rel=storage_rel,
                src_path=original_abs,
                lang=lang,
                on_status=_on_status_callback,
                storage_client=storage_client,
            )
            c = await get_conn()
            try:
                await set_video_captions(c, video_id, rel_vtt, meta.get("lang") or lang, meta)
            finally:
                await release_conn(c)
            print(f"[YTCMS] captions done video_id={video_id} lang={meta.get('lang')} vtt={rel_vtt}")
            _set_job_state(video_id, status="done", percent=100, job_id=meta.get("job_id"))
        except Exception as e:
            print(f"[YTCMS] captions failed video_id={video_id}: {e}")
            _set_job_state(video_id, status="fail", percent=-1, job_id=None)
        finally:
            if tmp_dir and os.path.isdir(tmp_dir):
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass

    asyncio.create_task(_bg_worker())
    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


@router.get("/internal/ytcms/captions/status")
async def captions_status(video_id: str = Query(...)):
    """
    Normalized status for UI:
    status: idle | wait | process | done | fail
    percent: -1 if unknown
    has_vtt / rel_vtt / lang / job_id
    """
    conn = await get_conn()
    try:
        row = await get_video_captions_status(conn, video_id)
    finally:
        await release_conn(conn)

    rel_vtt = None
    lang = None
    ready = False
    meta = None
    job_id = None
    job_server = None

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
        if isinstance(meta, dict):
            job_id = meta.get("job_id") or job_id
            job_server = meta.get("job_server") or job_server

    js = _get_job_state(video_id)
    now = time.time()

    if ready or rel_vtt:
        return {
            "ok": True,
            "video_id": video_id,
            "status": "done",
            "percent": 100,
            "has_vtt": True,
            "rel_vtt": rel_vtt,
            "lang": lang,
            "job_id": job_id or (js.get("job_id") if js else None),
            "job_server": job_server,
        }

    if js:
        js_status = js.get("status")
        js_percent = js.get("percent", -1)
        return {
            "ok": True,
            "video_id": video_id,
            "status": js_status or "wait",
            "percent": int(js_percent if isinstance(js_percent, (int, float)) else -1),
            "has_vtt": False,
            "rel_vtt": None,
            "lang": lang,
            "job_id": job_id or js.get("job_id"),
            "job_server": job_server,
        }

    prev = _JOB_STATE.get(video_id) or {}
    last_pct = int(prev.get("last_active_percent", -1)) if isinstance(prev.get("last_active_percent", -1), (int, float)) else -1
    last_pct_ts = float(prev.get("last_active_percent_ts", 0.0))
    if 0 < last_pct < 100 and (now - last_pct_ts) <= PERCENT_ACTIVE_GRACE_SEC:
        return {
            "ok": True,
            "video_id": video_id,
            "status": "process",
            "percent": last_pct,
            "has_vtt": False,
            "rel_vtt": None,
            "lang": lang,
            "job_id": job_id or prev.get("job_id"),
            "job_server": job_server,
        }

    last_st = prev.get("last_process_status")
    last_st_ts = float(prev.get("last_process_status_ts", 0.0))
    if last_st in ("wait", "process") and (now - last_st_ts) <= PREV_STATUS_GRACE_SEC:
        return {
            "ok": True,
            "video_id": video_id,
            "status": "wait",
            "percent": -1,
            "has_vtt": False,
            "rel_vtt": None,
            "lang": lang,
            "job_id": job_id or prev.get("job_id"),
            "job_server": job_server,
        }

    return {
        "ok": True,
        "video_id": video_id,
        "status": "idle",
        "percent": -1,
        "has_vtt": False,
        "rel_vtt": None,
        "lang": lang,
        "job_id": job_id or prev.get("job_id"),
        "job_server": job_server,
    }


@router.post("/internal/ytcms/captions/retry")
async def captions_retry(
    request: Request,
    video_id: str = Form(...),
    lang: str = Form("auto"),
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

    storage_client: StorageClient = request.app.state.storage
    original_rel = os.path.join(storage_rel, "original.webm")

    try:
        original_abs, tmp_dir = await _ensure_local_original(storage_client, original_rel)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    async def _bg_worker():
        _set_job_state(video_id, status="wait", percent=-1, job_id=None)
        try:
            rel_vtt, meta = await generate_captions(
                video_id=video_id,
                storage_rel=storage_rel,
                src_path=original_abs,
                lang=lang,
                on_status=_on_status_callback,
                storage_client=storage_client,
            )
            c = await get_conn()
            try:
                await set_video_captions(c, video_id, rel_vtt, meta.get("lang") or lang, meta)
            finally:
                await release_conn(c)
            print(f"[YTCMS] captions retry done video_id={video_id} lang={meta.get('lang')} vtt={rel_vtt}")
            _set_job_state(video_id, status="done", percent=100, job_id=meta.get("job_id"))
        except Exception as e:
            print(f"[YTCMS] captions retry failed video_id={video_id}: {e}")
            _set_job_state(video_id, status="fail", percent=-1, job_id=None)
        finally:
            if tmp_dir and os.path.isdir(tmp_dir):
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass

    asyncio.create_task(_bg_worker())
    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)


async def _storage_rmtree(storage: StorageClient, rel_dir: str) -> None:
    """
    Recursively remove a directory and its contents via StorageClient.
    Strategy:
    1) Prefer server-side recursive remove: storage.remove(rel_dir, recursive=True) if supported.
    2) Fallback: list children and remove them individually, handling both async and sync APIs,
       and both 'list of names' and 'protobuf response with entries'.
    3) Final local fallback via storage.to_abs for locally-backed storage.
    """
    # Try server-side recursive remove first
    try:
        rm = None
        try:
            rm = storage.remove(rel_dir, recursive=True)
        except TypeError:
            rm = storage.remove(rel_dir)
        except Exception:
            rm = None
        if rm is not None:
            if inspect.isawaitable(rm):
                await rm
            return
    except Exception:
        pass

    # Fallback: list children
    names_or_resp = None
    try:
        names_or_resp = storage.listdir(rel_dir)
        if inspect.isawaitable(names_or_resp):
            names_or_resp = await names_or_resp
    except Exception:
        names_or_resp = None

    # Normalize entries
    entries: Iterable[str] = []
    try:
        if isinstance(names_or_resp, (list, tuple)):
            entries = [str(x) for x in names_or_resp]
        elif names_or_resp is not None:
            resp = names_or_resp
            ent = getattr(resp, "entries", None)
            if ent and isinstance(ent, (list, tuple)):
                tmp = []
                for e in ent:
                    rp = getattr(e, "rel_path", None)
                    nm = getattr(e, "name", None)
                    if isinstance(rp, str) and rp:
                        tmp.append(rp)
                    elif isinstance(nm, str) and nm:
                        tmp.append(os.path.join(rel_dir, nm))
                entries = tmp
    except Exception:
        entries = []

    # Remove children
    for child in list(entries):
        child_rel = child if child.startswith(rel_dir) else os.path.join(rel_dir, child)
        try:
            rm = None
            try:
                rm = storage.remove(child_rel)
            except Exception:
                rm = None
            if rm is not None and inspect.isawaitable(rm):
                await rm
        except Exception:
            try:
                await _storage_rmtree(storage, child_rel)
            except Exception:
                # Local fallback
                try:
                    abs_child = storage.to_abs(child_rel)
                    if os.path.isdir(abs_child):
                        for root, dirs, files in os.walk(abs_child, topdown=False):
                            for f in files:
                                try:
                                    os.remove(os.path.join(root, f))
                                except Exception:
                                    pass
                            for d in dirs:
                                try:
                                    os.rmdir(os.path.join(root, d))
                                except Exception:
                                    pass
                        try:
                            os.rmdir(abs_child)
                        except Exception:
                            pass
                except Exception:
                    pass

    # Try removing dir itself again
    try:
        rm2 = None
        try:
            rm2 = storage.remove(rel_dir)
        except Exception:
            rm2 = None
        if rm2 is not None and inspect.isawaitable(rm2):
            await rm2
    except Exception:
        # Local fallback
        try:
            abs_dir = storage.to_abs(rel_dir)
            if os.path.isdir(abs_dir):
                for root, dirs, files in os.walk(abs_dir, topdown=False):
                    for f in files:
                        try:
                            os.remove(os.path.join(root, f))
                        except Exception:
                            pass
                    for d in dirs:
                        try:
                            os.rmdir(os.path.join(root, d))
                        except Exception:
                            pass
                try:
                    os.rmdir(abs_dir)
                except Exception:
                    pass
        except Exception:
            pass


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
        # Reset DB state first so UI reflects deletion immediately
        await reset_video_captions(conn, video_id)
        _clear_job_state(video_id)
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    captions_rel_dir = storage_client.join(storage_rel, "captions")

    # Remove directory tree
    await _storage_rmtree(storage_client, captions_rel_dir)

    return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)