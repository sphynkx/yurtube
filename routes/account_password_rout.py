from typing import Any, List, Tuple, Optional
import os
import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_conn, release_conn
from db.users_auth_db import get_user_auth_by_uid, update_user_password_hash
from utils.security_ut import get_current_user, verify_password, hash_password
from config.config import settings

try:
    from zxcvbn import zxcvbn  # type: ignore
    ZXCVBN_AVAILABLE = True
except Exception:
    ZXCVBN_AVAILABLE = False

# Configurable minimal score (0..4). If set via env PASSWORD_MIN_SCORE.
# Typical thresholds: 0 very weak, 1 weak, 2 reasonable, 3 strong, 4 very strong.
try:
    PASSWORD_MIN_SCORE = int(os.getenv("PASSWORD_MIN_SCORE", "2"))
except Exception:
    PASSWORD_MIN_SCORE = 2
PASSWORD_MIN_SCORE = max(0, min(PASSWORD_MIN_SCORE, 4))  # clamp


router = APIRouter()
templates = Jinja2Templates(directory="templates")

# --- CSRF helpers ---

def _gen_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def _get_csrf_cookie(request: Request) -> str:
    name = getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf")
    return (request.cookies.get(name) or "").strip()

def _validate_csrf(request: Request, form_token: Optional[str]) -> bool:
    cookie_tok = _get_csrf_cookie(request)
    header_tok = (request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or "").strip()
    qs_tok = (request.query_params.get("csrf_token") or "").strip()
    form_tok = (form_token or "").strip() or header_tok or qs_tok
    if cookie_tok and form_tok:
        try:
            import secrets as _sec
            return _sec.compare_digest(cookie_tok, form_tok)
        except Exception:
            return False
    return False


def _evaluate_password(pw: str) -> Tuple[List[str], List[str]]:
    """
    Return (errors, suggestions).
    Only errors block the form.
    Suggestions are informational (displayed if any) and DO NOT block.
    Policy:
      - If zxcvbn available: score must be >= PASSWORD_MIN_SCORE
      - Fallback baseline: length >= 8 AND at least 2 different char classes
    """
    s = (pw or "").strip()
    errors: List[str] = []
    suggestions: List[str] = []

    if ZXCVBN_AVAILABLE:
        try:
            res = zxcvbn(s)
            score = int(res.get("score", 0))
            # Blocking only if below threshold
            if score < PASSWORD_MIN_SCORE:
                errors.append(
                    f"Password score too low (score={score}, required>={PASSWORD_MIN_SCORE})."
                )
                # Show primary warning if available
                fb = res.get("feedback", {}) or {}
                warning = fb.get("warning")
                if isinstance(warning, str) and warning.strip():
                    suggestions.append(warning.strip())
            # Collect suggestions separately (non-blocking)
            for sug in res.get("feedback", {}).get("suggestions", []) or []:
                if isinstance(sug, str) and sug.strip():
                    suggestions.append(sug.strip())
        except Exception:
            # If zxcvbn blows up fall back
            pass

    if not ZXCVBN_AVAILABLE:
        # Minimal fallback policy
        if len(s) < 8:
            errors.append("Password must be at least 8 characters long.")
        lowers = any("a" <= c <= "z" for c in s)
        uppers = any("A" <= c <= "Z" for c in s)
        digits = any("0" <= c <= "9" for c in s)
        specials = any(not c.isalnum() for c in s)
        classes = (1 if lowers else 0) + (1 if uppers else 0) + (1 if digits else 0) + (1 if specials else 0)
        if classes < 2:
            errors.append("Use at least two types of characters (e.g. letters + digits).")
        common = {"password", "12345678", "qwerty", "qwertyui", "letmein", "11111111", "abc123"}
        if s.lower() in common:
            errors.append("Password is too common.")
        # Add mild suggestions (non-blocking)
        if len(s) < 12:
            suggestions.append("Consider a longer password (12+ characters) for better security.")
        if classes == 2:
            suggestions.append("Add another character type (symbols or case mix) to strengthen it.")

    # Deduplicate while preserving order
    def _dedupe(items: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for it in items:
            if it not in seen:
                seen.add(it)
                out.append(it)
        return out

    return _dedupe(errors), _dedupe(suggestions)


@router.get("/account/password", response_class=HTMLResponse)
async def password_form(request: Request) -> Any:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    csrf_token = _get_csrf_cookie(request) or _gen_csrf_token()

    resp = templates.TemplateResponse(
        "account/account_password.html",
        {
            "request": request,
            "current_user": user,
            "errors": [],
            "suggestions": [],
            "saved": False,
            "min_score": PASSWORD_MIN_SCORE,
            "zxcvbn": ZXCVBN_AVAILABLE,
            "csrf_token": csrf_token,
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        },
        headers={"Cache-Control": "no-store"},
    )
    if not _get_csrf_cookie(request):
        resp.set_cookie(getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"),
                        csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return resp


@router.post("/account/password", response_class=HTMLResponse)
async def password_change(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: Optional[str] = Form(None),
) -> Any:

    if not _validate_csrf(request, csrf_token):
        return HTMLResponse("<h1>CSRF failed</h1>", status_code=403)

    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    cur = (current_password or "").strip()
    new = (new_password or "").strip()
    rep = (confirm_password or "").strip()

    errors: List[str] = []
    suggestions: List[str] = []

    if new != rep:
        errors.append("New password and confirmation do not match.")

    if not errors:
        pw_errors, pw_suggestions = _evaluate_password(new)
        errors.extend(pw_errors)
        suggestions.extend(pw_suggestions)

    if errors:
        csrf_out = _get_csrf_cookie(request) or _gen_csrf_token()
        resp = templates.TemplateResponse(
            "account/account_password.html",
            {
                "request": request,
                "current_user": user,
                "errors": errors,
                "suggestions": suggestions,
                "saved": False,
                "min_score": PASSWORD_MIN_SCORE,
                "zxcvbn": ZXCVBN_AVAILABLE,
                "csrf_token": csrf_out,
                "brand_logo_url": settings.BRAND_LOGO_URL,
                "brand_tagline": settings.BRAND_TAGLINE,
                "favicon_url": settings.FAVICON_URL,
                "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
            },
            headers={"Cache-Control": "no-store"},
        )
        if not _get_csrf_cookie(request):
            resp.set_cookie(getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"),
                            csrf_out, httponly=False, secure=True, samesite="lax", path="/")
        return resp

    conn = await get_conn()
    try:
        auth = await get_user_auth_by_uid(conn, user["user_uid"])
        if not auth or not auth.get("password_hash"):
            errors.append("This account does not support local password login.")
        else:
            ok = False
            try:
                ok = verify_password(cur, auth["password_hash"])
            except Exception:
                ok = False
            if not ok:
                errors.append("Current password is incorrect.")

        if errors:
            csrf_out = _get_csrf_cookie(request) or _gen_csrf_token()
            resp = templates.TemplateResponse(
                "account/account_password.html",
                {
                    "request": request,
                    "current_user": user,
                    "errors": errors,
                    "suggestions": suggestions,
                    "saved": False,
                    "min_score": PASSWORD_MIN_SCORE,
                    "zxcvbn": ZXCVBN_AVAILABLE,
                    "csrf_token": csrf_out,
                    "brand_logo_url": settings.BRAND_LOGO_URL,
                    "brand_tagline": settings.BRAND_TAGLINE,
                    "favicon_url": settings.FAVICON_URL,
                    "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
                },
                headers={"Cache-Control": "no-store"},
            )
            if not _get_csrf_cookie(request):
                resp.set_cookie(getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"),
                                csrf_out, httponly=False, secure=True, samesite="lax", path="/")
            return resp

        new_hash = hash_password(new)
        await update_user_password_hash(conn, user["user_uid"], new_hash)

    finally:
        await release_conn(conn)

    csrf_out = _get_csrf_cookie(request) or _gen_csrf_token()
    resp = templates.TemplateResponse(
        "account/account_password.html",
        {
            "request": request,
            "current_user": user,
            "errors": [],
            "suggestions": suggestions,
            "saved": True,
            "min_score": PASSWORD_MIN_SCORE,
            "zxcvbn": ZXCVBN_AVAILABLE,
            "csrf_token": csrf_out,
            "brand_logo_url": settings.BRAND_LOGO_URL,
            "brand_tagline": settings.BRAND_TAGLINE,
            "favicon_url": settings.FAVICON_URL,
            "apple_touch_icon_url": settings.APPLE_TOUCH_ICON_URL,
        },
        headers={"Cache-Control": "no-store"},
    )
    if not _get_csrf_cookie(request):
        resp.set_cookie(getattr(settings, "CSRF_COOKIE_NAME", "yt_csrf"),
                        csrf_out, httponly=False, secure=True, samesite="lax", path="/")
    return resp