from typing import Any

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


## Fix annoying 404s in logs..
@router.get("/favicon.ico")
async def favicon() -> Any:
    return RedirectResponse("/static/img/YT_fav32.png", status_code=302)