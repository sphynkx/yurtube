import os
import time
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from services.ytadmin.grpc_server_srv import app_grpc_server
from services.monitor.uptime import uptime

from config.config import settings
from config.ytstorage.ytstorage_remote_cfg import STORAGE_PROVIDER
from config.ytstorage.ytstorage_cfg import APP_STORAGE_FS_ROOT

from routes import register_routes
from services.ytstorage.build_client_srv import build_storage_client

from middlewares.csrf_mw import NewCSRFMiddleware


# Toggle built-in API docs
docs_url    = "/docs" if settings.API_DOCS_ENABLED else None
redoc_url   = "/redoc" if settings.API_DOCS_ENABLED else None
openapi_url = "/openapi.json" if settings.API_DOCS_ENABLED else None

app = FastAPI(
    title="YurTube",
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)
APP_GRPC_ENABLED = os.getenv("APP_GRPC_ENABLED", "1").lower() in ("1","true","yes","on")
## Generate autoversioning number for js-scripts (updates on every app restart)
app.state.static_version = str(int(time.time()))


@app.on_event("startup")
async def on_startup():
    logging.basicConfig(level=logging.INFO)
    uptime.set_started()
    if APP_GRPC_ENABLED:
        await app_grpc_server.start()


@app.on_event("shutdown")
async def on_shutdown():
    if APP_GRPC_ENABLED:
        await app_grpc_server.stop()


from services.ytstorage.build_client_srv import build_storage_client
from config.config import settings


@app.on_event("startup")
async def on_startup():
    app.state.storage = build_storage_client(kind=STORAGE_PROVIDER)


app.add_middleware(NewCSRFMiddleware, cookie_name=getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"))


# Static and storage mounts
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount local /storage only for local provider
_provider = (STORAGE_PROVIDER or "").strip().lower()
if _provider == "local":
    if isinstance(APP_STORAGE_FS_ROOT, str) and os.path.isdir(APP_STORAGE_FS_ROOT):
        app.mount("/storage", StaticFiles(directory=APP_STORAGE_FS_ROOT), name="storage")


# Proxy / headers (behind reverse proxy)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])


# Minimal cookie session middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)


# Register routes
register_routes(app)
##print(f"ENABLED ROUTES: {app.routes}")