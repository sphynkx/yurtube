from typing import Any, Dict, List, Optional
import io
import inspect

from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url
from services.ytstorage.base_srv import StorageClient

from db.playlists_db import (
    add_video_to_watch_later,
    add_video_to_favorites,
    list_user_playlists_min,
    add_video_to_playlist,
    create_user_playlist,
    get_playlist_owner_uid,
    get_owned_playlist,
    list_playlist_items_with_assets,
    update_playlist_name,
    get_playlist_cover_path,
    set_playlist_cover_path,
    delete_playlist_by_owner,
    remove_video_from_playlist,
    reorder_playlist_items,
    update_playlist_visibility,
)

router = APIRouter(prefix="/playlists", tags=["playlists"])

templates = Jinja2Templates(directory="templates")
templates.env.globals["sitename"] = settings.SITENAME
templates.env.globals["support_email"] = settings.SUPPORT_EMAIL


def _get_csrf_cookie(request: Request) -> str:
    name = getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")
    return (request.cookies.get(name) or "").strip()


def _validate_csrf(request: Request) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    if cookie_tok and (header_tok or qs_tok):
        import secrets as _sec
        form_tok = header_tok or qs_tok
        try:
            return _sec.compare_digest(cookie_tok, form_tok)
        except Exception:
            return False
    return False


@router.post("/watch_later")
async def api_watch_later(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    video_id = (body.get("video_id") or "").strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        ok = await add_video_to_watch_later(conn, user["user_uid"], video_id)
        return JSONResponse({"ok": bool(ok)})
    finally:
        await release_conn(conn)


@router.post("/favorites")
async def api_favorites(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    video_id = (body.get("video_id") or "").strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        ok = await add_video_to_favorites(conn, user["user_uid"], video_id)
        return JSONResponse({"ok": bool(ok)})
    finally:
        await release_conn(conn)


@router.post("/add")
async def api_add_to_playlist(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    playlist_id = (body.get("playlist_id") or "").strip()
    video_id = (body.get("video_id") or "").strip()
    if not playlist_id or not video_id:
        raise HTTPException(status_code=400, detail="playlist_id_and_video_id_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        owner_uid = await get_playlist_owner_uid(conn, playlist_id)
        if not owner_uid or owner_uid != user["user_uid"]:
            raise HTTPException(status_code=403, detail="not_owner")
        ok = await add_video_to_playlist(conn, playlist_id, video_id)
        return JSONResponse({"ok": bool(ok)})
    finally:
        await release_conn(conn)


@router.post("/create")
async def api_create_playlist(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    name = (body.get("name") or "").strip()
    visibility = (body.get("visibility") or "private").strip().lower()

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        plid = await create_user_playlist(conn, user["user_uid"], name, visibility)
        return JSONResponse({"playlist_id": plid})
    finally:
        await release_conn(conn)


@router.get("/my")
async def api_my_playlists(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    conn = await get_conn()
    try:
        rows = await list_user_playlists_min(conn, user["user_uid"], limit=200)
        return JSONResponse({"items": rows})
    finally:
        await release_conn(conn)


@router.get("/", response_class=HTMLResponse)
async def playlists_page(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    conn = await get_conn()
    try:
        items = await list_user_playlists_min(conn, user["user_uid"], limit=500)
    finally:
        await release_conn(conn)

    for it in items:
        cov = it.get("cover_asset_path")
        it["cover_url"] = build_storage_url(cov) if cov else None

    context = {
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_tagline": settings.BRAND_TAGLINE,
        "favicon_url": settings.FAVICON_URL,
        "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        "request": request,
        "current_user": user,
        "playlists": items,
        "title": "Playlists",
    }
    return templates.TemplateResponse("playlists.html", context)


@router.get("/{playlist_id}/edit", response_class=HTMLResponse)
async def playlist_edit_page(request: Request, playlist_id: str) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    conn = await get_conn()
    try:
        pl = await get_owned_playlist(conn, playlist_id, user["user_uid"])
        if not pl:
            raise HTTPException(status_code=404, detail="not_found")

        rows = await list_playlist_items_with_assets(conn, playlist_id)
    finally:
        await release_conn(conn)

    def _with_ver(url: Optional[str], ver: Optional[int]) -> Optional[str]:
        if not url:
            return url
        try:
            v = int(ver or 0)
        except Exception:
            v = 0
        if v <= 0:
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}v={v}"

    items: List[Dict[str, Any]] = []
    for r in rows:
        it = dict(r)
        thumb_path = it.get("thumb_asset_path")
        ver = it.get("thumb_pref_offset")
        it["thumb_url"] = _with_ver(build_storage_url(thumb_path), ver) if thumb_path else None
        anim_asset = it.get("thumb_anim_asset_path")
        it["thumb_anim_url"] = _with_ver(build_storage_url(anim_asset), ver) if anim_asset else None
        items.append(it)

    cover_url = build_storage_url(pl.get("cover_asset_path")) if pl.get("cover_asset_path") else None

    context = {
        "brand_logo_url": settings.BRAND_LOGO_URL,
        "brand_tagline": settings.BRAND_TAGLINE,
        "favicon_url": settings.FAVICON_URL,
        "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        "request": request,
        "current_user": user,
        "playlist": pl,
        "cover_url": cover_url,
        "items": items,
        "title": "Edit playlist",
    }
    return templates.TemplateResponse("playlist_edit.html", context)


@router.post("/{playlist_id}/rename")
async def api_rename_playlist(request: Request, playlist_id: str) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        await update_playlist_name(conn, playlist_id, user["user_uid"], name)
        return JSONResponse({"ok": True})
    finally:
        await release_conn(conn)


@router.post("/{playlist_id}/visibility")
async def api_update_visibility(request: Request, playlist_id: str) -> Any:
    """
    JSON body: { "visibility": "private|unlisted|public" }
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body = await request.json()
    except Exception:
        body = {}
    visibility = (body.get("visibility") or "").strip().lower()
    if visibility not in ("private", "unlisted", "public"):
        raise HTTPException(status_code=400, detail="invalid_visibility")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        await update_playlist_visibility(conn, playlist_id, user["user_uid"], visibility)
        return JSONResponse({"ok": True})
    finally:
        await release_conn(conn)


@router.post("/{playlist_id}/cover")
async def api_upload_cover(request: Request, playlist_id: str, file: UploadFile = File(...)) -> Any:
    """
    Multipart: file=<image>
    Save the cover to storage: users/<USERID>/playlists/<PLAYLIST_ID>/cover.webp
    Support for async/sync StorageClient, as in upload_rout.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    data = await file.read()
    if not data or len(data) < 10:
        raise HTTPException(status_code=400, detail="empty_file")

    storage: StorageClient = request.app.state.storage
    rel_dir = storage.join("users", user["user_uid"], "playlists", playlist_id)
    rel_path = storage.join(rel_dir, "cover.webp")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        target_w, target_h = 480, 270
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h
        if img_ratio > target_ratio:
            new_w = int(img.height * target_ratio)
            x0 = (img.width - new_w) // 2
            img = img.crop((x0, 0, x0 + new_w, img.height))
        else:
            new_h = int(img.width / target_ratio)
            y0 = (img.height - new_h) // 2
            img = img.crop((0, y0, img.width, y0 + new_h))
        img = img.resize((target_w, target_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=85)
        out = buf.getvalue()
    except Exception:
        out = data

    mkdirs_res = storage.mkdirs(rel_dir, exist_ok=True)
    if inspect.isawaitable(mkdirs_res):
        await mkdirs_res

    writer_ctx = storage.open_writer(rel_path, overwrite=True)
    if inspect.isawaitable(writer_ctx):
        writer_ctx = await writer_ctx

    try:
        if hasattr(writer_ctx, "__aenter__"):
            async with writer_ctx as w:
                wr = w.write(out)
                if inspect.isawaitable(wr):
                    await wr
        else:
            with writer_ctx as w:
                w.write(out)
    except Exception:
        raise HTTPException(status_code=500, detail="storage_error")

    conn = await get_conn()
    try:
        await set_playlist_cover_path(conn, playlist_id, user["user_uid"], rel_path)
    finally:
        await release_conn(conn)

    return JSONResponse({"ok": True, "cover_url": build_storage_url(rel_path)})


@router.post("/{playlist_id}/cover/delete")
async def api_delete_cover(request: Request, playlist_id: str) -> Any:
    """
    Delete the cover file from storage and reset cover_asset_path in the database.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        rel_path = await get_playlist_cover_path(conn, playlist_id, user["user_uid"])
    finally:
        await release_conn(conn)

    if rel_path:
        storage: StorageClient = request.app.state.storage
        try:
            rm_res = storage.remove(rel_path)
            if inspect.isawaitable(rm_res):
                await rm_res
        except Exception:
            pass

    conn = await get_conn()
    try:
        await set_playlist_cover_path(conn, playlist_id, user["user_uid"], None)
    finally:
        await release_conn(conn)

    return JSONResponse({"ok": True})


@router.post("/{playlist_id}/delete")
async def api_delete_playlist(request: Request, playlist_id: str) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")
    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        rel_path = await get_playlist_cover_path(conn, playlist_id, user["user_uid"])
    finally:
        await release_conn(conn)

    if rel_path:
        storage: StorageClient = request.app.state.storage
        try:
            rm_res = storage.remove(rel_path)
            if inspect.isawaitable(rm_res):
                await rm_res
        except Exception:
            pass

    conn = await get_conn()
    try:
        await delete_playlist_by_owner(conn, playlist_id, user["user_uid"])
        return JSONResponse({"ok": True})
    finally:
        await release_conn(conn)


@router.post("/{playlist_id}/items/remove")
async def api_remove_item(request: Request, playlist_id: str) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body = await request.json()
    except Exception:
        body = {}
    video_id = (body.get("video_id") or "").strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        await remove_video_from_playlist(conn, playlist_id, video_id)
        return JSONResponse({"ok": True})
    finally:
        await release_conn(conn)


@router.post("/{playlist_id}/items/reorder")
async def api_reorder_items(request: Request, playlist_id: str) -> Any:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        body = await request.json()
    except Exception:
        body = {}

    order = body.get("order") or []
    if not isinstance(order, list) or not order:
        raise HTTPException(status_code=400, detail="order_required")

    if not _validate_csrf(request):
        raise HTTPException(status_code=403, detail="csrf_required")

    conn = await get_conn()
    try:
        await reorder_playlist_items(conn, playlist_id, [str(x) for x in order])
        return JSONResponse({"ok": True})
    finally:
        await release_conn(conn)