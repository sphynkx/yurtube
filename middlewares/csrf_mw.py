from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

def _is_https(request: Request) -> bool:
    xf_proto = (request.headers.get("x-forwarded-proto") or "").lower().strip()
    if xf_proto in ("https", "wss"):
        return True
    fwd = (request.headers.get("forwarded") or "").lower()
    if "proto=https" in fwd:
        return True
    return request.url.scheme == "https"

class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Issues a CSRF cookie for secure methods. Doesn't block anything.
    Validation is performed by routes (double-submit cookie).
    """
    def __init__(self, app, cookie_name: str = "yt_csrf"):
        super().__init__(app)
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: Callable):
        method = request.method.upper()
        resp = await call_next(request)
        if method in SAFE_METHODS:
            if not (request.cookies.get(self.cookie_name) or "").strip():
                import secrets
                token = secrets.token_urlsafe(32)
                resp.set_cookie(
                    self.cookie_name,
                    token,
                    httponly=False,
                    secure=_is_https(request),
                    samesite="lax",
                    path="/",
                )
        return resp