from fastapi import FastAPI

from .account_rout import router as account_router
from .auth_rout import router as auth_router
from .browse_rout import router as browse_router
from .channel_rout import router as channel_router
from .history_rout import router as history_router
from .root_rout import router as root_router
from .static_rout import router as static_router
from .upload_rout import router as upload_router
from .watch_rout import router as watch_router


def register_routes(app: FastAPI) -> None:
    app.include_router(root_router)
    app.include_router(auth_router, prefix="/auth")
    app.include_router(upload_router)
    app.include_router(watch_router)
    app.include_router(browse_router)
    app.include_router(channel_router)
    app.include_router(history_router)
    app.include_router(account_router)
    app.include_router(static_router)