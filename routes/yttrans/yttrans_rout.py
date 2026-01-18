from __future__ import annotations
import os
import json
import inspect
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.videos_db import get_owned_video
from utils.security_ut import get_current_user

from services.ytstorage.base_srv import StorageClient
from services.yttrans.yttrans_client_srv import (
    list_languages,
    submit_translate,
    get_status,
    get_partial_result,
    get_result,
)

router = APIRouter(tags=["yttrans"])
templates = Jinja2Templates(directory="templates")


def _csrf_cookie_name() -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")


def _get_csrf_cookie(request: Request) -> str:
    return (request.cookies.get(_csrf_cookie_name()) or "").strip()


def _validate_csrf(request: Request, form_token: Optional[str]) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    form_tok = (form_token or "").strip()
    if not cookie_tok or not form_tok:
        return False
    try:
        import secrets as _sec
        return _sec.compare_digest(cookie_tok, form_tok)
    except Exception:
        return False


def _lang_display_name_en(code: str) -> str:
    """
    Convert BCP47/ISO code (e.g. 'en', 'pt-BR', 'zh-Hans') to English display name using Babel.
    Falls back to the code itself if unknown / Babel missing.
    """
    c = (code or "").strip()
    if not c:
        return ""
    try:
        from babel.core import Locale  # type: ignore

        loc_code = c.replace("-", "_")
        try:
            loc = Locale.parse(loc_code)
        except Exception:
            base = loc_code.split("_", 1)[0]
            loc = Locale.parse(base)
        name = loc.get_display_name("en")
        if not name:
            return c
        return name[:1].upper() + name[1:]
    except Exception:
        return c


async def _read_text(storage_client: StorageClient, rel_path: str, encoding: str = "utf-8") -> str:
    reader_ctx = storage_client.open_reader(rel_path)
    if inspect.isawaitable(reader_ctx):
        reader_ctx = await reader_ctx
    data = b""
    if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
        async for chunk in reader_ctx:
            if chunk:
                data += chunk
    else:
        for chunk in reader_ctx:
            if chunk:
                data += chunk
    try:
        return data.decode(encoding, "replace")
    except Exception:
        return data.decode("utf-8", "replace")


async def _write_bytes(storage_client: StorageClient, rel_path: str, data: bytes) -> None:
    w = storage_client.open_writer(rel_path, overwrite=True)
    if inspect.isawaitable(w):
        w = await w
    if hasattr(w, "__aenter__"):
        async with w as f:
            wr = f.write(data)
            if inspect.isawaitable(wr):
                await wr
    else:
        with w as f:
            f.write(data)


async def _touch_dir(storage_client: StorageClient, rel_dir: str) -> None:
    mk = storage_client.mkdirs(rel_dir, exist_ok=True)
    if inspect.isawaitable(mk):
        await mk


async def _read_translations_meta(storage_client: StorageClient, storage_rel: str) -> Dict[str, Any]:
    rel = os.path.join(storage_rel.rstrip("/"), "captions", "translations.meta.json")
    ex = storage_client.exists(rel)
    if inspect.isawaitable(ex):
        ex = await ex
    if not ex:
        return {
            "video_id": "",
            "source_lang": "",
            "default_lang": "",
            "langs": [],
            "engine": "",
            "updated_at": "",
            "format_version": 1,
            "job_id": "",
            "job_server": "",
            "job_state": "",
            "job_message": "",
            "job_result_fetched": False,
        }
    try:
        txt = await _read_text(storage_client, rel, encoding="utf-8")
        meta = json.loads(txt or "{}")
        if not isinstance(meta, dict):
            meta = {}
        meta.setdefault("video_id", "")
        meta.setdefault("source_lang", "")
        meta.setdefault("default_lang", "")
        meta.setdefault("langs", [])
        meta.setdefault("engine", "")
        meta.setdefault("updated_at", "")
        meta.setdefault("format_version", 1)
        meta.setdefault("job_id", "")
        meta.setdefault("job_server", "")
        meta.setdefault("job_state", "")
        meta.setdefault("job_message", "")
        meta.setdefault("job_result_fetched", False)
        return meta
    except Exception:
        return {
            "video_id": "",
            "source_lang": "",
            "default_lang": "",
            "langs": [],
            "engine": "",
            "updated_at": "",
            "format_version": 1,
            "job_id": "",
            "job_server": "",
            "job_state": "",
            "job_message": "",
            "job_result_fetched": False,
        }


async def _write_translations_meta(storage_client: StorageClient, storage_rel: str, meta: Dict[str, Any]) -> None:
    rel = os.path.join(storage_rel.rstrip("/"), "captions", "translations.meta.json")
    await _touch_dir(storage_client, os.path.dirname(rel))
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    await _write_bytes(storage_client, rel, payload)


@router.get("/manage/video/{video_id}/translations", response_class=HTMLResponse)
async def video_translations_page(request: Request, video_id: str) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        storage_rel = owned["storage_path"].rstrip("/")
        storage_client: StorageClient = request.app.state.storage

        captions_rel = os.path.join(storage_rel, "captions", "captions.vtt")
        ex = storage_client.exists(captions_rel)
        if inspect.isawaitable(ex):
            has_captions = bool(await ex)
        else:
            has_captions = bool(ex)

        langs: List[str] = []
        default_src: str = "auto"
        meta: Dict[str, Any] = {}
        if has_captions:
            try:
                langs, default_src, meta = await list_languages()
            except Exception as e:
                langs = []
                default_src = "auto"
                meta = {"error": f"{e}"}

        trans_meta = await _read_translations_meta(storage_client, storage_rel)
        existing_langs: List[str] = []
        try:
            existing_langs = list(trans_meta.get("langs") or [])
        except Exception:
            existing_langs = []

        target_langs_view: List[Dict[str, str]] = []
        for code in (langs or []):
            c = (code or "").strip()
            if not c:
                continue
            target_langs_view.append({"code": c, "name": _lang_display_name_en(c)})
        # Sort by display name
        target_langs_view.sort(key=lambda x: ((x.get("name") or "").lower(), (x.get("code") or "").lower()))

        csrf_token = _get_csrf_cookie(request)
        return templates.TemplateResponse(
            "manage/video_translations.html",
            {
                "request": request,
                "current_user": user,
                "video_id": video_id,
                "has_captions": has_captions,
                "target_langs": target_langs_view,
                "default_source_lang": default_src,
                "yttrans_meta": meta,
                "existing_langs": existing_langs,
                "csrf_token": csrf_token,
                "brand_logo_url": settings.BRAND_LOGO_URL,
                "brand_tagline": settings.BRAND_TAGLINE,
                "favicon_url": settings.FAVICON_URL,
                "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
            },
            headers={"Cache-Control": "no-store"},
        )
    finally:
        await release_conn(conn)


@router.post("/manage/video/{video_id}/translations/generate", response_class=HTMLResponse)
async def translations_generate(
    request: Request,
    video_id: str,
    csrf_token: Optional[str] = Form(None),
    lang: List[str] = Form([]),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf(request, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)

    target_langs = [l.strip() for l in (lang or []) if l.strip()]
    if not target_langs:
        return RedirectResponse(url=f"/manage/video/{video_id}/translations", status_code=303)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        storage_rel = owned["storage_path"].rstrip("/")
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    captions_rel = os.path.join(storage_rel, "captions", "captions.vtt")
    ex = storage_client.exists(captions_rel)
    if inspect.isawaitable(ex):
        ex = await ex
    if not ex:
        return RedirectResponse(url=f"/manage/video/{video_id}/media", status_code=303)

    try:
        src_vtt = await _read_text(storage_client, captions_rel, encoding="utf-8")
    except Exception:
        src_vtt = "WEBVTT\n\n"

    try:
        job_id, job_server = await submit_translate(
            video_id=video_id,
            src_vtt=src_vtt,
            src_lang="auto",
            target_langs=target_langs,
            options=None,
        )
    except Exception as e:
        print(f"[YTTRANS] submit failed video_id={video_id}: {e}")
        return RedirectResponse(url=f"/manage/video/{video_id}/translations", status_code=303)

    # Persist job id immediately
    try:
        trans_meta = await _read_translations_meta(storage_client, storage_rel)
        trans_meta["video_id"] = video_id
        trans_meta["job_id"] = job_id
        trans_meta["job_server"] = job_server
        trans_meta["job_state"] = "running"
        trans_meta["job_message"] = ""
        trans_meta["job_result_fetched"] = False
        import time
        trans_meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        await _write_translations_meta(storage_client, storage_rel, trans_meta)
    except Exception as e:
        print(f"[YTTRANS] meta job_id write failed video_id={video_id}: {e}")

    async def _bg_worker() -> None:
        print(
            f"[YTTRANS] job queued video_id={video_id} job_id={job_id} server={job_server} langs={target_langs}"
        )
        try:
            pr: Dict[str, Any] = {
                "state": "running",
                "percent": -1,
                "message": "",
                "ready_langs": [],
                "total_langs": 0,
            }

            # Poll partial until DONE/FAILED
            for _ in range(900):  # ~15 min
                pr = await get_partial_result(job_id, server=job_server)

                # Persist last known status (optional, used by UI)
                try:
                    trans_meta2 = await _read_translations_meta(storage_client, storage_rel)
                    trans_meta2["job_id"] = job_id
                    trans_meta2["job_server"] = job_server
                    trans_meta2["job_state"] = pr.get("state") or trans_meta2.get("job_state") or ""
                    trans_meta2["job_message"] = pr.get("message") or trans_meta2.get("job_message") or ""
                    import time
                    trans_meta2["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    await _write_translations_meta(storage_client, storage_rel, trans_meta2)
                except Exception:
                    pass

                st = (pr.get("state") or "").lower()
                if st in ("done", "failed"):
                    break

                await asyncio.sleep(1.0)

            if (pr.get("state") or "").lower() != "done":
                print(
                    f"[YTTRANS] job failed video_id={video_id} job_id={job_id} server={job_server} msg={pr.get('message')}"
                )
                return

            # DONE: fetch VTT exactly once (one-shot contract)
            trans_meta3 = await _read_translations_meta(storage_client, storage_rel)
            if bool(trans_meta3.get("job_result_fetched")):
                print(f"[YTTRANS] result already fetched (skip) video_id={video_id} job_id={job_id}")
                return

            vid, default_lang, entries, meta = await get_result(job_id, server=job_server)

            captions_dir = os.path.join(storage_rel, "captions")
            await _touch_dir(storage_client, captions_dir)

            wrote_langs: List[str] = []
            for lang_code, vtt_text in entries:
                if not lang_code:
                    continue
                rel = os.path.join(captions_dir, f"{lang_code}.vtt")
                try:
                    await _write_bytes(storage_client, rel, (vtt_text or "").encode("utf-8"))
                    wrote_langs.append(lang_code)
                except Exception as e:
                    print(f"[YTTRANS] write failed lang={lang_code} video_id={video_id}: {e}")

            trans_meta = await _read_translations_meta(storage_client, storage_rel)
            existing = set(trans_meta.get("langs") or [])
            for l in wrote_langs:
                existing.add(l)
            trans_meta["langs"] = sorted(existing)
            if default_lang:
                trans_meta["default_lang"] = default_lang
            elif not trans_meta.get("default_lang"):
                trans_meta["default_lang"] = "auto"
            trans_meta["video_id"] = video_id
            trans_meta["engine"] = meta.get("engine") or trans_meta.get("engine") or ""
            trans_meta["job_id"] = job_id
            trans_meta["job_server"] = job_server
            trans_meta["job_state"] = "done"
            trans_meta["job_message"] = ""
            trans_meta["job_result_fetched"] = True
            import time
            trans_meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            await _write_translations_meta(storage_client, storage_rel, trans_meta)
            print(f"[YTTRANS] translations written video_id={video_id} langs={wrote_langs}")
        except Exception as e:
            print(f"[YTTRANS] worker failed video_id={video_id}: {e}")

    asyncio.create_task(_bg_worker())
    return RedirectResponse(url=f"/manage/video/{video_id}/translations", status_code=303)


@router.post("/manage/video/{video_id}/translations/delete", response_class=HTMLResponse)
async def translations_delete(
    request: Request,
    video_id: str,
    csrf_token: Optional[str] = Form(None),
    lang: List[str] = Form([]),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf(request, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)

    target_langs = [l.strip() for l in (lang or []) if l.strip()]
    if not target_langs:
        return RedirectResponse(url=f"/manage/video/{video_id}/translations", status_code=303)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        storage_rel = owned["storage_path"].rstrip("/")
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    captions_dir = os.path.join(storage_rel, "captions")

    for l in target_langs:
        rel = os.path.join(captions_dir, f"{l}.vtt")
        try:
            rm = storage_client.remove(rel)
            if inspect.isawaitable(rm):
                await rm
        except Exception:
            pass

    trans_meta = await _read_translations_meta(storage_client, storage_rel)
    exist = set(trans_meta.get("langs") or [])
    for l in target_langs:
        if l in exist:
            exist.remove(l)
    trans_meta["langs"] = sorted(exist)
    if trans_meta.get("default_lang") in target_langs:
        src_lang = trans_meta.get("source_lang") or ""
        if src_lang and src_lang in trans_meta["langs"]:
            trans_meta["default_lang"] = src_lang
        elif trans_meta["langs"]:
            trans_meta["default_lang"] = trans_meta["langs"][0]
        else:
            trans_meta["default_lang"] = "auto"
    import time
    trans_meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    await _write_translations_meta(storage_client, storage_rel, trans_meta)

    return RedirectResponse(url=f"/manage/video/{video_id}/translations", status_code=303)


@router.post("/manage/video/{video_id}/translations/reset_all", response_class=HTMLResponse)
async def translations_reset_all(
    request: Request,
    video_id: str,
    csrf_token: Optional[str] = Form(None),
) -> Any:
    """
    Hard reset translations state for video:
    - removes captions/*.vtt except captions.vtt
    - removes captions/translations.meta.json
    Fixes issues then service fail or redis was cleaned.. and job is removed on other side. Permit 502 errors.
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf(request, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        storage_rel = owned["storage_path"].rstrip("/")
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    captions_dir = os.path.join(storage_rel, "captions").rstrip("/")

    # 1) list caption dir and delete all *.vtt except captions.vtt
    # StorageClient API differs between backends; try common patterns.
    removed_any = False
    try:
        # Prefer listdir if exists
        if hasattr(storage_client, "listdir"):
            items = storage_client.listdir(captions_dir)
            if inspect.isawaitable(items):
                items = await items

            # items could be names or dicts; normalize to string names
            names: List[str] = []
            for it in (items or []):
                if isinstance(it, str):
                    names.append(it)
                elif isinstance(it, dict):
                    n = (it.get("name") or it.get("key") or it.get("path") or "")
                    if n:
                        names.append(str(n))
                else:
                    n = getattr(it, "name", None) or getattr(it, "key", None) or getattr(it, "path", None)
                    if n:
                        names.append(str(n))

            for name in names:
                # name might be "en.vtt" or "captions/en.vtt"
                base = name.split("/")[-1]
                if not base.endswith(".vtt"):
                    continue
                if base == "captions.vtt":
                    continue
                rel = os.path.join(captions_dir, base)
                try:
                    rm = storage_client.remove(rel)
                    if inspect.isawaitable(rm):
                        await rm
                    removed_any = True
                except Exception:
                    pass
    except Exception:
        # if listing isn't supported, we still can at least delete meta
        pass

    # 2) remove translations meta
    meta_rel = os.path.join(captions_dir, "translations.meta.json")
    try:
        rm = storage_client.remove(meta_rel)
        if inspect.isawaitable(rm):
            await rm
        removed_any = True
    except Exception:
        # Fallback: overwrite meta with empty reset structure (so UI stops polling job_id)
        try:
            trans_meta = await _read_translations_meta(storage_client, storage_rel)
            trans_meta["video_id"] = video_id
            trans_meta["langs"] = []
            trans_meta["default_lang"] = "auto"
            trans_meta["job_id"] = ""
            trans_meta["job_server"] = ""
            trans_meta["job_state"] = ""
            trans_meta["job_message"] = ""
            trans_meta["job_result_fetched"] = False
            import time
            trans_meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            await _write_translations_meta(storage_client, storage_rel, trans_meta)
            removed_any = True
        except Exception:
            pass

    return RedirectResponse(url=f"/manage/video/{video_id}/translations", status_code=303)


@router.get("/internal/yttrans/translations/status")
async def translations_status(request: Request, video_id: str = Query(...)) -> Any:
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        storage_rel = owned["storage_path"].rstrip("/")
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    meta = await _read_translations_meta(storage_client, storage_rel)
    langs = list(meta.get("langs") or [])
    default_lang = meta.get("default_lang") or ""
    job_id = meta.get("job_id") or ""
    job_state = meta.get("job_state") or ""
    job_message = meta.get("job_message") or ""
    return JSONResponse(
        {
            "ok": True,
            "langs": langs,
            "default_lang": default_lang,
            "job_id": job_id,
            "job_state": job_state,
            "job_message": job_message,
        }
    )


@router.get("/internal/yttrans/translations/progress")
async def translations_progress(request: Request, video_id: str = Query(...)) -> Any:
    """
    UI polling endpoint:
    - Uses GetPartialResult during QUEUED/RUNNING/DONE/FAILED
    - Never calls GetResult (one-shot)
    - Also returns langs_written from translations.meta.json (actual stored VTT files)
    """
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)

    conn = await get_conn()
    try:
        owned = await get_owned_video(conn, video_id, user["user_uid"])
        if not owned:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        storage_rel = owned["storage_path"].rstrip("/")
    finally:
        await release_conn(conn)

    storage_client: StorageClient = request.app.state.storage
    meta = await _read_translations_meta(storage_client, storage_rel)

    saved_langs = list(meta.get("langs") or [])
    job_id = (meta.get("job_id") or "").strip()
    job_server = (meta.get("job_server") or "").strip()
    default_lang = meta.get("default_lang") or ""

    if not job_id:
        return JSONResponse(
            {
                "ok": True,
                "job_id": "",
                "state": meta.get("job_state") or "",
                "percent": -1,
                "message": meta.get("job_message") or "",
                "ready_langs": [],
                "total_langs": 0,
                "langs_written": saved_langs,
                "default_lang": default_lang,
            }
        )

    try:
        pr = await get_partial_result(job_id, server=job_server or None)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"partial_failed:{e}"}, status_code=502)

    return JSONResponse(
        {
            "ok": True,
            "job_id": job_id,
            "state": pr.get("state") or "",
            "percent": int(pr.get("percent", -1)),
            "message": pr.get("message") or "",
            "ready_langs": list(pr.get("ready_langs") or []),
            "total_langs": int(pr.get("total_langs", 0) or 0),
            "langs_written": saved_langs,
            "default_lang": default_lang,
        }
    )