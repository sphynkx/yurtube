from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
import inspect

from db import get_conn, release_conn
from utils.security_ut import get_current_user
from db.videos_query_db import get_owned_video_full as db_get_owned_video_full
from db.ytconvert.ytconvert_jobs_db import create_ytconvert_job
from services.ytconvert.ytconvert_runner_srv import schedule_ytconvert_job
from db.video_renditions_db import delete_video_rendition
from db.ytconvert.video_assets_db import delete_video_asset_by_type
from services.ytstorage.base_srv import StorageClient
from utils.ytconvert.variants_ut import expand_requested_variant_ids

router = APIRouter()

# NOTE: edit_rout.py has _validate_csrf implementation; here we either:
#  - import it (not great), OR
#  - implement minimal same-cookie compare here.
# For consistency, best move is to share CSRF util in one module, but for now:


def _get_csrf_cookie(request: Request) -> str:
    from config.config import settings
    name = getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")
    return (request.cookies.get(name) or "").strip()


def _validate_csrf_simple(request: Request, form_token: Optional[str]) -> bool:
    import secrets
    cookie = _get_csrf_cookie(request)
    tok = (form_token or "").strip()
    if not cookie or not tok:
        return False
    try:
        return secrets.compare_digest(cookie, tok)
    except Exception:
        return False


async def delete_video_rendition(conn, *, video_id: str, preset: str, codec: str) -> Optional[str]:
    """
    Delete a rendition row and return its storage_path (if any).
    """
    row = await conn.fetchrow(
        """
        DELETE FROM video_renditions
        WHERE video_id = $1 AND preset = $2 AND codec = $3
        RETURNING storage_path
        """,
        video_id,
        preset,
        codec,
    )
    return (row["storage_path"] if row and "storage_path" in row else None)


@router.post("/manage/edit/ytconvert/queue")
async def ytconvert_queue_from_edit(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    ytconvert_variants: Optional[List[str]] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf_simple(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    requested = []
    if ytconvert_variants:
        requested = [str(x).strip() for x in ytconvert_variants if str(x).strip()]

    if not requested:
        return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)

    requested = expand_requested_variant_ids(requested)

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        storage_rel = str(owned["storage_path"] or "").strip().strip("/")
        original_rel_path = f"{storage_rel}/original.webm"

        local_job_id = await create_ytconvert_job(
            conn,
            video_id=video_id,
            author_uid=user["user_uid"],
            requested_variants=requested,
        )

    finally:
        await release_conn(conn)

    # fire job
    try:
        schedule_ytconvert_job(
            request=request,
            local_job_id=local_job_id,
            video_id=video_id,
            storage_rel=storage_rel,
            original_rel_path=original_rel_path,
            requested_variant_ids=requested,
        )
    except Exception as e:
        # keep user on edit, but show something in logs
        print(f"[EDIT] ytconvert scheduling failed video_id={video_id}: {e}")

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


@router.post("/manage/edit/ytconvert/delete")
async def ytconvert_delete_selected(
    request: Request,
    video_id: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    del_items: Optional[List[str]] = Form(None),
) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    if not _validate_csrf_simple(request, csrf_token):
        raise HTTPException(status_code=403, detail="csrf_required")

    items = [str(x).strip() for x in (del_items or []) if str(x).strip()]
    if not items:
        return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)

    storage_client: StorageClient = request.app.state.storage

    conn = await get_conn()
    try:
        owned = await db_get_owned_video_full(conn, video_id, user["user_uid"])
        if not owned:
            raise HTTPException(status_code=404, detail="Video not found")

        # Best-effort: delete files then rows; if file delete fails - still remove row.
        for token in items:
            # token format:
            #  - "v|<preset>|<codec>"
            #  - "a|<asset_type>"
            parts = token.split("|")
            if not parts:
                continue

            kind = parts[0]
            storage_path = None

            if kind == "v" and len(parts) >= 3:
                preset = parts[1]
                codec = parts[2]
                storage_path = await delete_video_rendition(conn, video_id=video_id, preset=preset, codec=codec)

            elif kind == "a" and len(parts) >= 2:
                asset_type = parts[1]
                storage_path = await delete_video_asset_by_type(conn, video_id=video_id, asset_type=asset_type)

            # delete file (best-effort)
            if storage_path:
                try:
                    rm = storage_client.remove(storage_path, recursive=False)  # type: ignore
                    if inspect.isawaitable(rm):
                        await rm
                except Exception:
                    pass

    finally:
        await release_conn(conn)

    return RedirectResponse(f"/manage/edit?v={video_id}", status_code=302)


