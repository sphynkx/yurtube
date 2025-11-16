import secrets
from typing import Optional
from fastapi import Request, Response

DEFAULT_COOKIE_NAME = "yt_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_cookie_name(settings) -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", DEFAULT_COOKIE_NAME)


def gen_token() -> str:
    return secrets.token_urlsafe(32)


def read_cookie_token(request: Request, settings) -> str:
    name = get_cookie_name(settings)
    return (request.cookies.get(name) or "").strip()


def is_https(request: Request) -> bool:
    xf_proto = (request.headers.get("x-forwarded-proto") or "").lower().strip()
    if xf_proto in ("https", "wss"):
        return True
    fwd = (request.headers.get("forwarded") or "").lower()
    if "proto=https" in fwd:
        return True
    return request.url.scheme == "https"


def set_cookie_token(request: Request, resp: Response, token: str, settings) -> None:
    resp.set_cookie(
        get_cookie_name(settings),
        token,
        httponly=False,
        secure=is_https(request),
        samesite="lax",
        path="/",
    )


async def extract_supplied_token(request: Request) -> str:
    """
    Returns a token from:
    - X-CSRF-Token header (AJAX),
    - form body (csrf_token) for application/x-www-form-urlencoded and multipart/form-data,
    - JSON body (csrf_token) if needed,
    - (deprecated) query parameter for smooth migration (can be removed after the transition).
    Starlette caches form/json; re-requesting in a route is safe.
    """
    # Header
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    if header_tok:
        return header_tok

    ctype = (request.headers.get("content-type") or "").lower()

    # Form-urlencoded / multipart
    if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
        try:
            form = await request.form()
            val = (form.get("csrf_token") or "").strip()
            if val:
                return val
        except Exception:
            pass

    # JSON
    if "application/json" in ctype:
        try:
            data = await request.json()
            if isinstance(data, dict):
                val = (data.get("csrf_token") or "").strip()
                if val:
                    return val
        except Exception:
            pass

    # deprecated fallback (2DEL)
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    if qs_tok:
        return qs_tok

    return ""


def validate_csrf(cookie_token: str, supplied_token: str) -> bool:
    if not cookie_token or not supplied_token:
        return False
    try:
        import secrets as _sec
        return _sec.compare_digest(cookie_token, supplied_token)
    except Exception:
        return False