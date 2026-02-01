from typing import Any, Dict, List, Optional
import os
import re
import json
import asyncio
import secrets
from urllib.parse import urlparse
import tempfile

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset
from db.categories_db import list_categories
from db.video_renditions_db import list_video_renditions as db_list_renditions, enqueue_video_renditions
from db.videos_query_db import (
    get_owned_video_full as db_get_owned_video_full,
    update_video_meta as db_update_video_meta,
    update_thumb_pref_offset as db_update_thumb_pref_offset,
    set_video_embed_params as db_set_video_embed_params,
)
from services.ffmpeg_srv import (
    async_generate_thumbnails,
    async_generate_animated_preview,
)
from services.search.indexer_srch import fire_and_forget_reindex, reindex_video
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url

# --- Storage abstraction ---
from services.ytstorage.base_srv import StorageClient

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["sitename"] = settings.SITENAME
templates.env.globals["support_email"] = settings.SUPPORT_EMAIL


def _bool_from_form(val: Optional[str]) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on", "y", "t"):
        return True
    if s in ("0", "false", "no", "off", "n", "f"):
        return False
    return False


async def _fetch_owned_video_full(conn, video_id: str, owner_uid: str) -> Optional[Dict[str, Any]]:
    """
    Fetch owned video with related assets for edit pages.
    NOTE: DB access is delegated to db.videos_query_db.get_owned_video_full.
    """
    return await db_get_owned_video_full(conn, video_id, owner_uid)


async def _list_renditions(conn, video_id: str) -> List[Dict[str, Any]]:
    """
    List renditions for a video (status, codec, preset, etc).
    NOTE: DB access is delegated to db.video_renditions_db.list_video_renditions.
    """
    return await db_list_renditions(conn, video_id)


# CSRF helpers (local copy)
def _gen_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _get_csrf_cookie(request: Request) -> str:
    name = getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")
    return (request.cookies.get(name) or "").strip()


def _same_origin(request: Request, origin: str) -> bool:
    try:
        req_host = request.headers.get("host", "")
        u = urlparse(origin)
        return bool(u.netloc) and (u.netloc == req_host)
    except Exception:
        return False


def _validate_csrf(request: Request, form_token: Optional[str]) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    form_tok = (form_token or "").strip() or header_tok or qs_tok

    if cookie_tok and form_tok:
        try:
            return secrets.compare_digest(cookie_tok, form_tok)
        except Exception:
            return False

    # dev fallback
    if not cookie_tok and form_tok and _same_origin(request, request.headers.get("origin") or request.headers.get("referer") or ""):
        return True

    return False


@router.get("/edit/{video_id}", response_class=HTMLResponse)
async def edit_page_legacy_path(request: Request, video_id: str) -> Any:
    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


@router.get("/manage/edit/{video_id}", response_class=HTMLResponse)
async def edit_page_path(request: Request, video_id: str) -> Any:
    return await edit_page(request, v=video_id)


@router.get("/manage/edit", response_class=HTMLResponse)
async def edit_page(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        video = await _fetch_owned_video_full(conn, v, user["user_uid"])
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        e = video.get("embed_params")
        if isinstance(e, str):
            try:
                e = json.loads(e) if e.strip() else {}
            except Exception:
                e = {}
        if not isinstance(e, dict):
            e = {}
        video["embed_params"] = e

        for key, default_val in (
            ("title", ""),
            ("description", ""),
            ("status", "private"),
            ("license", "standard"),
            ("category_id", None),
            ("permit_download", False),
            ("is_age_restricted", False),
            ("is_made_for_kids", False),
            ("allow_comments", True),
            ("allow_embed", True),
            ("thumb_pref_offset", 0),
        ):
            if key not in video or video[key] is None:
                video[key] = default_val

        tap = video.get("thumb_asset_path")
        video["thumb_url"] = build_storage_url(tap) if tap else None

        cats = await list_categories(conn)
        categories = [dict(c) for c in cats]

        renditions = await _list_renditions(conn, v)

        presets_str = (getattr(settings, "DEFAULT_RENDITION_PRESETS", "1080p,720p,480p,360p") or "").strip()
        presets = [p.strip() for p in presets_str.split(",") if p.strip()]
    finally:
        await release_conn(conn)

    csrf_token = _gen_csrf_token()
    resp = templates.TemplateResponse(
        "manage/edit_video.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "current_user": user,
            "video": video,
            "categories": categories,
            "presets": presets,
            "renditions": renditions,
            "csrf_token": csrf_token,
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
        },
        headers={"Cache-Control": "no-store"},
    )
    resp.set_cookie(getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"), csrf_token, httponly=False, samesite="none", secure=True, path="/")
    return resp


@router.post("/manage/edit/meta")
async def edit_meta(
    request: Request,
    background_tasks: BackgroundTasks,
    video_id: str = Form(...),
    title: str = Form(""),
    description: str = Form(""),
    status: str = Form(...),
    category_id: Optional[str] = Form(None),
    permit_download: Optional[str] = Form(None),
    is_age_restricted: Optional[str] = Form(None),
    is_made_for_kids: Optional[str] = Form(None),
    allow_comments: Optional[str] = Form(None),
    license: str = Form("standard"),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    if status not in ("public", "private", "unlisted"):
        raise HTTPException(status_code=400, detail="Invalid status")

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        old = dict(owned)
        new_title = title.strip() if title is not None and title.strip() != "" else old.get("title", "")
        new_desc = description if description is not None and description != "" else old.get("description", "")

        b_download = _bool_from_form(permit_download)
        b_age = _bool_from_form(is_age_restricted)
        b_kids = _bool_from_form(is_made_for_kids)
        b_comments = _bool_from_form(allow_comments)

        await db_update_video_meta(
            conn,
            video_id,
            title=new_title,
            description=new_desc,
            status=status,
            category_id=category_id,
            permit_download=b_download,
            is_age_restricted=b_age,
            is_made_for_kids=b_kids,
            allow_comments=b_comments,
            license_str=(license or "standard"),
        )
    finally:
        await release_conn(conn)

    background_tasks.add_task(reindex_video, video_id)
    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


# --- Storage helpers ---

async def _read_to_temp(sc: StorageClient, rel_path: str, suffix: str) -> str:
    """
    Materialize a storage file into a local temp file.
    Always uses reader (async for remote, sync for local).
    """
    tmp = tempfile.NamedTemporaryFile(prefix="yt_src_", suffix=suffix, delete=False)
    try:
        try:
            reader = await sc.open_reader(rel_path)  # type: ignore
            async for chunk in reader:
                if chunk:
                    tmp.write(chunk)
        except TypeError:
            f = sc.open_reader(rel_path)  # type: ignore
            try:
                while True:
                    buf = f.read(1024 * 1024)
                    if not buf:
                        break
                    tmp.write(buf)
            finally:
                try:
                    f.close()
                except Exception:
                    pass
        tmp.flush()
        return tmp.name
    finally:
        try:
            tmp.close()
        except Exception:
            pass


async def _write_bytes(sc: StorageClient, rel_path: str, src_path: str) -> None:
    """
    Write local file bytes into storage path.
    Uses async writer for remote and plain file write for local.
    """
    try:
        writer = await sc.open_writer(rel_path, overwrite=True)  # type: ignore
        async with writer as w:  # type: ignore
            with open(src_path, "rb") as rf:
                while True:
                    chunk = rf.read(1024 * 1024)
                    if not chunk:
                        break
                    await w.write(chunk)  # type: ignore
        return
    except TypeError:
        # Local storage
        abs_path = sc.to_abs(rel_path)  # type: ignore
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f, open(src_path, "rb") as rf:
            while True:
                ch = rf.read(1024 * 1024)
                if not ch:
                    break
                f.write(ch)


async def _write_upload(sc: StorageClient, rel_path: str, upl: UploadFile) -> None:
    """
    Write UploadFile stream to storage path.
    """
    try:
        writer = await sc.open_writer(rel_path, overwrite=True)  # type: ignore
        async with writer as w:  # type: ignore
            while True:
                chunk = await upl.read(1024 * 1024)
                if not chunk:
                    break
                await w.write(chunk)  # type: ignore
        return
    except TypeError:
        abs_path = sc.to_abs(rel_path)  # type: ignore
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            while True:
                ch = await upl.read(1024 * 1024)
                if not ch:
                    break
                f.write(ch)


@router.post("/manage/edit/thumb/regen")
async def regen_thumbs(
    request: Request,
    video_id: str = Form(...),
    offset_sec: int = Form(0),
    animate: Optional[str] = Form(None),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    # CSRF protection
    if not _validate_csrf(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    tmp_src = None
    tmp_out = None
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"]
        storage_client: StorageClient = request.app.state.storage

        original_rel = f"{rel_storage.strip('/')}/original.webm"
        thumbs_rel_dir = f"{rel_storage.strip('/')}/thumbs"

        # Ensure thumbs dir exists (for local it makes dirs; for remote the backend handles it)
        try:
            await storage_client.mkdirs(thumbs_rel_dir, exist_ok=True)  # type: ignore
        except TypeError:
            try:
                storage_client.mkdirs(thumbs_rel_dir, exist_ok=True)  # type: ignore
            except Exception:
                pass

        # Read source to temp
        tmp_src = await _read_to_temp(storage_client, original_rel, ".webm")
        tmp_out = tempfile.mkdtemp(prefix="yt_th_")

        # Static preview: thumb_custom.jpg
        static_list = await async_generate_thumbnails(tmp_src, tmp_out, [max(0, int(offset_sec))])
        if static_list:
            static_tmp = static_list[0]
            static_rel = f"{thumbs_rel_dir}/thumb_custom.jpg"
            await _write_bytes(storage_client, static_rel, static_tmp)
            await upsert_video_asset(conn, video_id, "thumbnail_default", static_rel)

        # Animated preview: keep stable name
        if _bool_from_form(animate):
            anim_tmp = os.path.join(tmp_out, "thumb_anim.webp")
            ok = await async_generate_animated_preview(tmp_src, anim_tmp, start_sec=max(0, int(offset_sec)), duration_sec=3, fps=12)
            if ok and os.path.exists(anim_tmp):
                anim_rel = f"{thumbs_rel_dir}/thumb_anim.webp"
                await _write_bytes(storage_client, anim_rel, anim_tmp)
                await upsert_video_asset(conn, video_id, "thumbnail_anim", anim_rel)

        # Save preferred offset
        await db_update_thumb_pref_offset(conn, video_id, max(0, int(offset_sec)))
    finally:
        await release_conn(conn)
        # Cleanup temp
        try:
            if tmp_src and os.path.isfile(tmp_src):
                os.remove(tmp_src)
        except Exception:
            pass
        try:
            if tmp_out and os.path.isdir(tmp_out):
                for n in os.listdir(tmp_out):
                    p = os.path.join(tmp_out, n)
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                try:
                    os.rmdir(tmp_out)
                except Exception:
                    pass
        except Exception:
            pass

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


@router.post("/manage/edit/thumb/upload")
async def upload_thumbs(
    request: Request,
    video_id: str = Form(...),
    thumb_static: Optional[UploadFile] = File(None),
    thumb_anim: Optional[UploadFile] = File(None),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    # CSRF protection
    if not _validate_csrf(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    if not thumb_static and not thumb_anim:
        return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"]
        storage_client: StorageClient = request.app.state.storage
        thumbs_rel_dir = f"{rel_storage.strip('/')}/thumbs"

        # Ensure thumbs dir
        try:
            await storage_client.mkdirs(thumbs_rel_dir, exist_ok=True)  # type: ignore
        except TypeError:
            try:
                storage_client.mkdirs(thumbs_rel_dir, exist_ok=True)  # type: ignore
            except Exception:
                pass

        if thumb_static:
            static_rel = f"{thumbs_rel_dir}/thumb_custom.jpg"
            await _write_upload(storage_client, static_rel, thumb_static)
            await upsert_video_asset(conn, video_id, "thumbnail_default", static_rel)

        if thumb_anim:
            anim_rel = f"{thumbs_rel_dir}/thumb_anim.webp"
            await _write_upload(storage_client, anim_rel, thumb_anim)
            await upsert_video_asset(conn, video_id, "thumbnail_anim", anim_rel)
    finally:
        await release_conn(conn)

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


@router.get("/manage/edit/thumb/pick", response_class=HTMLResponse)
async def pick_thumb_page(request: Request, v: str = Query(..., min_length=12, max_length=12)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, v, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"]
        thumbs_rel_dir = f"{rel_storage.strip('/')}/thumbs".replace("\\", "/").strip("/")
        storage_client: StorageClient = request.app.state.storage

        items: List[Dict[str, str]] = []

        # list via StorageClient (works for both local and remote)
        try:
            exists_res = storage_client.exists(thumbs_rel_dir)  # type: ignore
            if hasattr(exists_res, "__await__"):
                exists_res = await exists_res  # type: ignore

            if bool(exists_res):
                names: List[str] = []

                # Try remote-style listdir (async, dict with entries)
                try:
                    res = storage_client.listdir(thumbs_rel_dir)  # type: ignore
                    if hasattr(res, "__await__"):
                        res = await res  # type: ignore

                    if isinstance(res, dict) and "entries" in res:
                        for e in (res.get("entries") or []):
                            if not isinstance(e, dict):
                                continue
                            nm = (e.get("name") or "").strip()
                            if nm:
                                names.append(nm)
                            else:
                                # fallback: derive name from rel_path
                                rp = (e.get("rel_path") or "").replace("\\", "/").strip("/")
                                if rp:
                                    names.append(rp.rsplit("/", 1)[-1])
                    else:
                        # Local-style listdir (iterable of names)
                        try:
                            for nm in res:  # type: ignore
                                if nm:
                                    names.append(str(nm))
                        except TypeError:
                            names = []
                except Exception:
                    names = []

                names = sorted(set(n.strip() for n in names if n and str(n).strip()))

                for name in names:
                    # show thumb_*.jpg and also thumb_custom.jpg if present
                    if re.match(r"^thumb_.*\.jpg$", name) or name == "thumb_custom.jpg":
                        rel = f"{thumbs_rel_dir}/{name}".replace("\\", "/").lstrip("/")
                        items.append({"rel": rel, "url": build_storage_url(rel)})
        except Exception:
            pass

        video = dict(owned)
    finally:
        await release_conn(conn)

    csrf_token = _gen_csrf_token()
    resp = templates.TemplateResponse(
        "manage/pick_thumbnail.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request,
            "current_user": user,
            "video": video,
            "candidates": items,
            "csrf_token": csrf_token,
            "storage_public_base_url": getattr(settings, "STORAGE_PUBLIC_BASE_URL", None),
        },
        headers={"Cache-Control": "no-store"},
    )

    # IMPORTANT: Secure cookie only works on HTTPS.
    # If you use HTTP in dev/LAN, cookie won't be saved, CSRF breaks.
    is_https = (request.url.scheme or "").lower() == "https"
    resp.set_cookie(
        getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"),
        csrf_token,
        httponly=False,
        samesite="none" if is_https else "lax",
        secure=True if is_https else False,
        path="/",
    )
    return resp


@router.post("/manage/edit/renditions")
async def set_renditions(
    request: Request,
    video_id: str = Form(...),
    presets: Optional[str] = Form(""),
    codec: Optional[str] = Form("vp9"),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    plist = [p.strip() for p in (presets or "").split(",") if p.strip()]
    if not plist:
        return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")
        await enqueue_video_renditions(conn, video_id, plist, (codec or "vp9"))
    finally:
        await release_conn(conn)

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


@router.post("/manage/edit/embed")
async def set_embed(
    request: Request,
    video_id: str = Form(...),
    allow_embed: Optional[str] = Form(None),
    autoplay: Optional[str] = Form(None),
    mute: Optional[str] = Form(None),
    loop: Optional[str] = Form(None),
    start_default: Optional[int] = Form(0),
    csrf_token: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    allow = _bool_from_form(allow_embed)
    params: Dict[str, Any] = {
        "autoplay": 1 if _bool_from_form(autoplay) else 0,
        "mute": 1 if _bool_from_form(mute) else 0,
        "loop": 1 if _bool_from_form(loop) else 0,
        "start": max(0, int(start_default or 0)),
    }

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        await db_set_video_embed_params(conn, video_id, allow, json.dumps(params))
    finally:
        await release_conn(conn)

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)