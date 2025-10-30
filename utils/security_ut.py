import base64
import hmac
import time
from hashlib import sha256
from typing import Any, Dict, Optional

from fastapi import Request, Response
from passlib.context import CryptContext

from config.config import settings

_pwd_ctx = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_ctx.verify(password, password_hash)


def _sign(value: str, ts: int) -> str:
    msg = f"{value}.{ts}".encode("ascii")
    mac = hmac.new(settings.SECRET_KEY.encode("ascii"), msg, sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def create_session_cookie(response: Response, user_uid: str) -> None:
    ts = int(time.time())
    exp = ts + settings.SESSION_TTL_SECONDS
    sig = _sign(user_uid, exp)
    payload = f"{user_uid}.{exp}.{sig}"
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=payload,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.SESSION_TTL_SECONDS,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.SESSION_COOKIE_NAME)


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not cookie:
        return None
    parts = cookie.split(".")
    if len(parts) != 3:
        return None
    user_uid, exp_str, sig = parts
    try:
        exp = int(exp_str)
    except ValueError:
        return None
    if exp < int(time.time()):
        return None
    if _sign(user_uid, exp) != sig:
        return None
    return {"user_uid": user_uid}