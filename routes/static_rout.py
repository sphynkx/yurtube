from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

router = APIRouter()

@router.get("/favicon.ico")
async def favicon() -> Any:
    path = Path("static/img/YT_fav32.png")
    return FileResponse(str(path))


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request) -> Any:
    return templates.TemplateResponse(
        "auth/privacy.html",
        {"request": request},
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request) -> Any:
    return templates.TemplateResponse(
        "auth/terms.html",
        {"request": request},
    )


@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request) -> Any:
    return templates.TemplateResponse("about.html", {"request": request})
