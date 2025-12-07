import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from config.config import settings
from routes import register_routes
from services.storage.build_client_srv import build_storage_client

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

from services.storage.build_client_srv import build_storage_client
from config.config import settings


@app.on_event("startup")
async def on_startup():
    app.state.storage = build_storage_client(kind=getattr(settings, "STORAGE_PROVIDER", ""))


app.add_middleware(NewCSRFMiddleware, cookie_name=getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"))


# Static and storage mounts
app.mount("/static", StaticFiles(directory="static"), name="static")


_storage_dir = getattr(settings, "APP_STORAGE_FS_ROOT", None)
if isinstance(_storage_dir, str) and os.path.isdir(_storage_dir):
    app.mount("/storage", StaticFiles(directory=_storage_dir), name="storage")


# Proxy / headers (behind reverse proxy)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])


# Minimal cookie session middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)


# Register routes
register_routes(app)
##print(f"ENABLED ROUTES: {app.routes}")