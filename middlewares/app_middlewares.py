from typing import Optional
import secrets
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

def _same_origin(request: Request, origin: str) -> bool:
    try:
        o = urlparse(origin)
        host_hdr = request.headers.get("host") or ""
        this = f"{request.url.scheme}://{host_hdr}"
        return (o.scheme + "://" + (o.netloc or "")).lower() == this.lower()
    except Exception:
        return False

class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Soft CSRF protection:
    - For insecure methods: check Origin (if any) and either tokens (cookie + X-CSRF-Token) or X-Requested-With.
    - Automatic CSRF cookie issuance: always for secure methods; also for 403, so the next POST will go through.
    """
    def __init__(self, app, settings):
        super().__init__(app)
        self.settings = settings

    def _set_cookie(self, resp: Response):
        resp.set_cookie(
            self.settings.CSRF_COOKIE_NAME,
            secrets.token_urlsafe(32),
            max_age=60 * 60 * 24 * 30,
            secure=True,
            samesite="lax",
            httponly=False,
            path="/",
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = (request.method or "").upper()
        unsafe = method in ("POST", "PUT", "PATCH", "DELETE")

        if unsafe:
            origin = request.headers.get("origin")
            if origin and not _same_origin(request, origin):
                resp = JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
                if not request.cookies.get(self.settings.CSRF_COOKIE_NAME):
                    self._set_cookie(resp)
                return resp

            cookie_name = self.settings.CSRF_COOKIE_NAME
            token_cookie = request.cookies.get(cookie_name) or ""
            token_hdr = request.headers.get("x-csrf-token") or ""
            xrw = (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest"

            ok = (token_cookie and token_hdr and secrets.compare_digest(token_cookie, token_hdr)) or xrw
            if not ok:
                resp = JSONResponse({"ok": False, "error": "csrf_required"}, status_code=403)
                if not token_cookie:
                    self._set_cookie(resp)
                return resp

        response = await call_next(request)

        # Guarantee CSRF-cookie on safe methods
        if method in ("GET", "HEAD", "OPTIONS") and not request.cookies.get(self.settings.CSRF_COOKIE_NAME):
            self._set_cookie(response)

        return response

class NotFoundRedirectMiddleware(BaseHTTPMiddleware):
    """
    Universal 404 handler:
    - HTML requests: 302 to the home page;
    - API/XHR (Accept: application/json without text/html): JSON 404;
    - static/service paths — as is.
    """
    def __init__(self, app, settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
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

def install_middlewares(app, settings) -> None:
    if getattr(settings, "CSRF_ENFORCE", False):
        app.add_middleware(CSRFMiddleware, settings=settings)
    if getattr(settings, "API_404_REDIRECT_ENABLED", True):
        app.add_middleware(NotFoundRedirectMiddleware, settings=settings)