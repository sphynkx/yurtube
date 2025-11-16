import secrets
from typing import Optional
from fastapi import Request, Response

DEFAULT_COOKIE_NAME = "yt_csrf"


def get_cookie_name(settings) -> str:
    return getattr(settings, "CSRF_COOKIE_NAME", DEFAULT_COOKIE_NAME)


def gen_token() -> str:
    return secrets.token_urlsafe(32)


def read_cookie_token(request: Request, settings) -> str:
    name = get_cookie_name(settings)
    return (request.cookies.get(name) or "").strip()


async def extract_supplied_token(request: Request) -> str:
    """
    Attempts to retrieve a token from the form body or header.
    Doesn't call parse twice thanks to the Starlette cache.
    """
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    if header_tok:
        return header_tok

    # if multipart or form-urlencoded
    ctype = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ctype or "application/x-www-form-urlencoded" in ctype:
        try:
            form = await request.form()
            val = (form.get("csrf_token") or "").strip()
            if val:
                return val
        except Exception:
            pass

    # (optionally) JSON body
    if "application/json" in ctype:
        try:
            data = await request.json()
            if isinstance(data, dict):
                val = (data.get("csrf_token") or "").strip()
                if val:
                    return val
        except Exception:
            pass

    # Old fallback: query param
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    if qs_tok:
        return qs_tok

    return ""


def is_https(request: Request) -> bool:
    xf_proto = (request.headers.get("x-forwarded-proto") or "").lower().strip()
    if xf_proto in ("https", "wss"):
        return True
    fwd = (request.headers.get("forwarded") or "").lower()
    if "proto=https" in fwd:
        return True
    return request.url.scheme == "https"


def set_cookie_token(request: Request, resp: Response, token: str, settings) -> None:
    secure_flag = is_https(request)
    resp.set_cookie(
        get_cookie_name(settings),
        token,
        httponly=False,
        secure=secure_flag,
        samesite="lax",
        path="/",
    )


def validate_csrf(cookie_token: str, supplied_token: str) -> bool:
    if not cookie_token or not supplied_token:
        return False
    try:
        import secrets as _sec
        return _sec.compare_digest(cookie_token, supplied_token)
    except Exception:
        return False