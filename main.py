import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from config.config import settings
from routes import register_routes

docs_url     = "/docs" if settings.API_DOCS_ENABLED else None
redoc_url    = "/redoc" if settings.API_DOCS_ENABLED else None
openapi_url  = "/openapi.json" if settings.API_DOCS_ENABLED else None

app = FastAPI(
    title="YurTube", 
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)
##app = FastAPI(title="YurTube", version="0.1.0")

# Static and storage mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
if os.path.isdir(settings.STORAGE_ROOT):
    app.mount("/storage", StaticFiles(directory=settings.STORAGE_ROOT), name="storage")

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])

# Minimal session middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# 404 handler via middleware:
# - for HTML-requests - redirect to main;
# - for API/XHR (Accept: application/json) - JSON 404;
# - no static/services
if settings.API_404_REDIRECT_ENABLED:
    @app.middleware("http")
    async def redirect_404_middleware(request, call_next):
        resp = await call_next(request)
        if resp.status_code != 404:
            return resp

        path = request.url.path or ""
        if path.startswith("/static/") or path in ("/favicon.ico", "/robots.txt", "/sitemap.xml"):
            return resp

        accept = (request.headers.get("accept") or "").lower()
        if "application/json" in accept and "text/html" not in accept:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

        return RedirectResponse("/", status_code=302)

# Register routes
register_routes(app)