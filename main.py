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
APP_GRPC_ENABLED = os.getenv("APP_GRPC_ENABLED", "1").lower() in ("1", "true", "yes", "on")
app.state.static_version = str(int(time.time()))


@app.on_event("startup")
async def on_startup():
    # Storage is always remote ytstorage now (STORAGE_PROVIDER deprecated)
    app.state.storage = build_storage_client(kind="")
    logging.basicConfig(level=logging.INFO)
    uptime.set_started()
    if APP_GRPC_ENABLED:
        await app_grpc_server.start()


@app.on_event("shutdown")
async def on_shutdown():
    if APP_GRPC_ENABLED:
        await app_grpc_server.stop()


app.add_middleware(NewCSRFMiddleware, cookie_name=getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"))

# Static mounts
app.mount("/static", StaticFiles(directory="static"), name="static")

# Proxy / headers (behind reverse proxy)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])

# Minimal cookie session middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Register routes
register_routes(app)