from fastapi import FastAPI

from .auth_rout import router as auth_router
from .root_rout import router as root_router
from .upload_rout import router as upload_router
from .watch_rout import router as watch_router


def register_routes(app: FastAPI) -> None:
    app.include_router(root_router)
    app.include_router(auth_router, prefix="/auth")
    app.include_router(upload_router)
    app.include_router(watch_router)