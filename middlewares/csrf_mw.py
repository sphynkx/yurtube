from typing import Callable, Iterable, Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _cookie_name(settings) -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")


def _is_https(request: Request) -> bool:
    xf_proto = (request.headers.get("x-forwarded-proto") or "").lower().strip()
    if xf_proto in ("https", "wss"):
        return True
    fwd = (request.headers.get("forwarded") or "").lower()
    if "proto=https" in fwd:
        return True
    return request.url.scheme == "https"


def _gen_token() -> str:
    import secrets as _sec
    return _sec.token_urlsafe(32)


class NewCSRFMiddleware(BaseHTTPMiddleware):
    """
    Only issues a CSRF cookie for SAFE methods. It doesn't read the request body at all.
    Validation is performed in routers (double-submit cookies).
    """
    def __init__(self, app, cookie_name: Optional[str] = None, skip_paths: Optional[Iterable[str]] = None):
        super().__init__(app)
        from config.config import settings
        self.settings = settings
        self.cookie_name = cookie_name or _cookie_name(settings)
        self._skip = tuple(skip_paths or ())

    def _skipped(self, path: str) -> bool:
        return any(path.startswith(p) for p in self._skip)

    async def dispatch(self, request: Request, call_next: Callable):
        if self._skipped(request.url.path):
            return await call_next(request)

        method = (request.method or "").upper()
        resp = await call_next(request)

        if method in SAFE_METHODS:
            if not (request.cookies.get(self.cookie_name) or "").strip():
                resp.set_cookie(
                    self.cookie_name,
                    _gen_token(),
                    httponly=False,
                    secure=_is_https(request),
                    samesite="lax",
                    path="/",
                )
        return resp