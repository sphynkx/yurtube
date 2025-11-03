from typing import Any, Dict, List, Optional
import os
import re
import json
import asyncio

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config.config import settings
from db import get_conn, release_conn
from db.assets_db import upsert_video_asset
from db.categories_db import list_categories
from services.ffmpeg_srv import (
    async_generate_thumbnails,
    async_generate_animated_preview,
)
from services.search.indexer_srch import fire_and_forget_reindex, reindex_video
from utils.security_ut import get_current_user
from utils.url_ut import build_storage_url


router = APIRouter()
templates = Jinja2Templates(directory="templates")


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
    row = await conn.fetchrow(
        """
        SELECT v.*,
               u.username, u.channel_id,
               ua.path AS avatar_asset_path,
               a.path AS thumb_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        WHERE v.video_id = $1 AND v.author_uid = $2
        """,
        video_id,
        owner_uid,
    )
    return dict(row) if row else None


async def _list_renditions(conn, video_id: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT preset, codec, status, storage_path, updated_at, error_message
        FROM video_renditions
        WHERE video_id = $1
        ORDER BY preset, codec
        """,
        video_id,
    )
    return [dict(r) for r in rows]


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

    return templates.TemplateResponse(
        "manage/edit_video.html",
        {
            "request": request,
            "current_user": user,
            "video": video,
            "categories": categories,
            "presets": presets,
            "renditions": renditions,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/manage/edit/meta")
async def edit_meta(
    request: Request,
    background_tasks: BackgroundTasks,
    video_id: str = Form(...),
    title: str = Form(""),
    description: str = Form(""),
    status: str = Form(...),
    category_id: Optional[str] = Form(None),
    is_age_restricted: Optional[str] = Form(None),
    is_made_for_kids: Optional[str] = Form(None),
    allow_comments: Optional[str] = Form(None),
    license: str = Form("standard"),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

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

        b_age = _bool_from_form(is_age_restricted)
        b_kids = _bool_from_form(is_made_for_kids)
        b_comments = _bool_from_form(allow_comments)

        await conn.execute(
            """
            UPDATE videos
            SET title = $2,
                description = $3,
                status = $4,
                category_id = $5,
                is_age_restricted = $6,
                is_made_for_kids = $7,
                allow_comments = $8,
                license = $9
            WHERE video_id = $1
            """,
            video_id,
            new_title,
            new_desc,
            status,
            (category_id or None),
            b_age,
            b_kids,
            b_comments,
            (license or "standard").strip(),
        )
    finally:
        await release_conn(conn)

    background_tasks.add_task(reindex_video, video_id)

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


@router.post("/manage/edit/thumb/regen")
async def regen_thumbs(
    request: Request,
    video_id: str = Form(...),
    offset_sec: int = Form(0),
    animate: Optional[str] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"]
        storage_dir = os.path.join(settings.STORAGE_ROOT, rel_storage)
        original_path = os.path.join(storage_dir, "original.webm")
        thumbs_dir = os.path.join(storage_dir, "thumbs")
        os.makedirs(thumbs_dir, exist_ok=True)

        tmp = await async_generate_thumbnails(original_path, thumbs_dir, [max(0, int(offset_sec))])
        if tmp:
            gen_path = tmp[0]
            out_static = os.path.join(thumbs_dir, "thumb_custom.jpg")
            if os.path.abspath(gen_path) != os.path.abspath(out_static):
                try:
                    if os.path.exists(out_static):
                        os.remove(out_static)
                except Exception:
                    pass
                os.replace(gen_path, out_static)
            rel_static = os.path.relpath(out_static, settings.STORAGE_ROOT)
            await upsert_video_asset(conn, video_id, "thumbnail_default", rel_static)

        if _bool_from_form(animate):
            anim_path = os.path.join(thumbs_dir, "thumb_anim.webp")
            ok_anim = await async_generate_animated_preview(
                original_path,
                anim_path,
                start_sec=max(0, int(offset_sec)),
                duration_sec=3,
                fps=12,
            )
            if ok_anim and os.path.exists(anim_path):
                rel_anim = os.path.relpath(anim_path, settings.STORAGE_ROOT)
                await upsert_video_asset(conn, video_id, "thumbnail_anim", rel_anim)

        await conn.execute(
            "UPDATE videos SET thumb_pref_offset = $2 WHERE video_id = $1",
            video_id,
            max(0, int(offset_sec)),
        )
    finally:
        await release_conn(conn)

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


@router.post("/manage/edit/thumb/upload")
async def upload_thumbs(
    request: Request,
    video_id: str = Form(...),
    thumb_static: Optional[UploadFile] = File(None),
    thumb_anim: Optional[UploadFile] = File(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not thumb_static and not thumb_anim:
        return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        rel_storage = owned["storage_path"]
        storage_dir = os.path.join(settings.STORAGE_ROOT, rel_storage)
        thumbs_dir = os.path.join(storage_dir, "thumbs")
        os.makedirs(thumbs_dir, exist_ok=True)

        if thumb_static:
            out_static = os.path.join(thumbs_dir, "thumb_custom.jpg")
            with open(out_static, "wb") as f:
                while True:
                    chunk = await thumb_static.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            rel = os.path.relpath(out_static, settings.STORAGE_ROOT)
            await upsert_video_asset(conn, video_id, "thumbnail_default", rel)

        if thumb_anim:
            out_anim = os.path.join(thumbs_dir, "thumb_anim.webp")
            with open(out_anim, "wb") as f:
                while True:
                    chunk = await thumb_anim.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            rel = os.path.relpath(out_anim, settings.STORAGE_ROOT)
            await upsert_video_asset(conn, video_id, "thumbnail_anim", rel)
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
        thumbs_dir = os.path.join(settings.STORAGE_ROOT, rel_storage, "thumbs")
        items: List[Dict[str, str]] = []
        if os.path.isdir(thumbs_dir):
            for name in sorted(os.listdir(thumbs_dir)):
                if re.match(r"^thumb_.*\.jpg$", name):
                    rel = os.path.join(rel_storage, "thumbs", name).replace("\\", "/")
                    items.append({"rel": rel, "url": build_storage_url(rel)})
        video = dict(owned)
    finally:
        await release_conn(conn)

    return templates.TemplateResponse(
        "manage/pick_thumbnail.html",
        {"request": request, "current_user": user, "video": video, "candidates": items},
    )


@router.post("/manage/edit/renditions")
async def set_renditions(
    request: Request,
    video_id: str = Form(...),
    presets: Optional[str] = Form(""),
    codec: Optional[str] = Form("vp9"),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    plist = [p.strip() for p in (presets or "").split(",") if p.strip()]
    if not plist:
        return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)

    conn = await get_conn()
    try:
        owned = await _fetch_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")
        for p in plist:
            await conn.execute(
                """
                INSERT INTO video_renditions (video_id, preset, codec, status)
                VALUES ($1, $2, $3, 'queued')
                ON CONFLICT (video_id, preset, codec)
                DO UPDATE SET status = 'queued', updated_at = now(), error_message = NULL
                """,
                video_id,
                p,
                (codec or "vp9").strip(),
            )
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
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

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

        await conn.execute(
            """
            UPDATE videos
            SET allow_embed = $2,
                embed_params = $3::jsonb
            WHERE video_id = $1
            """,
            video_id,
            allow,
            json.dumps(params),
        )
    finally:
        await release_conn(conn)

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)