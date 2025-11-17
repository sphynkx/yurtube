import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from config.config import settings
from routes import register_routes

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

app.add_middleware(NewCSRFMiddleware, cookie_name=getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"))

# Static and storage mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
if os.path.isdir(settings.STORAGE_ROOT):
    app.mount("/storage", StaticFiles(directory=settings.STORAGE_ROOT), name="storage")

# Proxy / headers (behind reverse proxy)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])

# Minimal cookie session middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Register routes
register_routes(app)