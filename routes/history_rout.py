from typing import Any

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse

from db import get_conn, release_conn
from db.views_db import clear_history, remove_history_for_video
from utils.security_ut import get_current_user

router = APIRouter()


@router.post("/history/clear")
async def history_clear(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    conn = await get_conn()
    try:
        await clear_history(conn, user["user_uid"])
    finally:
        await release_conn(conn)

    return RedirectResponse("/history", status_code=status.HTTP_302_FOUND)


@router.post("/history/remove")
async def history_remove(request: Request, video_id: str = Form(...)) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    conn = await get_conn()
    try:
        await remove_history_for_video(conn, user["user_uid"], video_id)
    finally:
        await release_conn(conn)

    return RedirectResponse("/history", status_code=status.HTTP_302_FOUND)