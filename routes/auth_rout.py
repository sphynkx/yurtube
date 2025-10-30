from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.users_db import authenticate_user, create_user, get_user_by_username
from utils.idgen_ut import gen_id
from utils.security_ut import (
    clear_session_cookie,
    create_session_cookie,
    get_current_user,
    hash_password,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Any:
    if get_current_user(request):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("auth/login.html", {"request": request, "current_user": None})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> Any:
    conn = await get_conn()
    try:
        user = await authenticate_user(conn, username, password)
    finally:
        await release_conn(conn)

    if not user:
        # Render the login page with a friendly error instead of JSON
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "current_user": None,
                "error": "Invalid username or password",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    create_session_cookie(redirect, user["user_uid"])
    return redirect


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> Any:
    if get_current_user(request):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("auth/register.html", {"request": request, "current_user": None})


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
) -> Any:
    conn = await get_conn()
    try:
        existing = await get_user_by_username(conn, username)
        if existing:
            return templates.TemplateResponse(
                "auth/register.html",
                {
                    "request": request,
                    "current_user": None,
                    "error": "Username already taken",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user_uid = gen_id(20)
        channel_id = gen_id(24)
        await create_user(
            conn=conn,
            user_uid=user_uid,
            channel_id=channel_id,
            username=username,
            email=email,
            password_hash=hash_password(password),
        )
    finally:
        await release_conn(conn)

    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    create_session_cookie(redirect, user_uid)
    return redirect


@router.post("/logout")
async def logout() -> Any:
    redirect = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(redirect)
    return redirect