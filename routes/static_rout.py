from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from config.config import settings

templates = Jinja2Templates(directory="templates")

router = APIRouter()

@router.get("/favicon.ico")
async def favicon() -> Any:
    path = Path(settings.FAVICON_URL.lstrip("/"))
    if not path.exists():
        path = Path("static/img/YT_fav32.png")
    return FileResponse(str(path))


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request) -> Any:
    return templates.TemplateResponse(
        "auth/privacy.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request
        },
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request) -> Any:
    return templates.TemplateResponse(
        "auth/terms.html",
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request
        },
    )


@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request) -> Any:
    return templates.TemplateResponse("about.html", 
        {
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            "request": request
        })
