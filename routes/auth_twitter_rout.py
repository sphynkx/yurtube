import base64
import json
import re
import secrets
import hashlib
from typing import Any, Dict, Optional
from urllib.parse import urlencode, quote_plus

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi import status

from utils.security_ut import create_session_cookie, get_current_user
from config.config import settings
from db.twitter_sso_flow_db import process_twitter_identity

router = APIRouter()

# Twitter OAuth 2.0 (PKCE + optional OIDC id_token when 'openid' is granted).
AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
ME_URL = "https://api.twitter.com/2/users/me"

def _build_state(code_verifier: str, link_mode: int) -> str:
    payload = {"v": code_verifier, "csrf": secrets.token_urlsafe(16), "link": link_mode}
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

def _parse_state(state: str) -> Optional[Dict[str, Any]]:
    try:
        padded = state + "=" * (-len(state) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        obj = json.loads(raw.decode("utf-8"))
        if isinstance(obj, dict) and "v" in obj and "csrf" in obj:
            if "link" not in obj:
                obj["link"] = 0
            return obj
    except Exception:
        return None
    return None

def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

def _normalized_scope() -> str:
    """
    Build a valid scope string:
    - If env is empty -> use safe default "tweet.read users.read offline.access"
    - Accept commas or spaces in env value; split on both.
    - Remove duplicates, keep order.
    - Drop 'openid' unless TWITTER_ENABLE_OIDC is true (to avoid invalid_scope).
    """
    raw = (settings.TWITTER_OAUTH_SCOPES or "").strip()
    if not raw:
        tokens = ["tweet.read", "users.read", "offline.access"]
    else:
        parts = re.split(r"[,\s]+", raw)
        tokens = [p for p in parts if p]

    if not settings.TWITTER_ENABLE_OIDC:
        tokens = [t for t in tokens if t.lower() != "openid"]

    seen = set()
    ordered = []
    for t in tokens:
        if t not in seen:
            ordered.append(t)
            seen.add(t)
    return " ".join(ordered)

@router.get("/auth/twitter/start")
async def twitter_start(request: Request, link: Optional[int] = 0) -> Any:
    if not settings.TWITTER_OAUTH_CLIENT_ID or not settings.TWITTER_OAUTH_REDIRECT_URL:
        if settings.TWITTER_OAUTH_DEBUG:
            print("[twitter-oauth] not configured",
                  "client_id=", repr(settings.TWITTER_OAUTH_CLIENT_ID),
                  "redirect=", repr(settings.TWITTER_OAUTH_REDIRECT_URL))
        return HTMLResponse("<h1>Twitter OAuth not configured</h1>", status_code=500)

    link_mode = 1 if str(link) == "1" else 0
    code_verifier = secrets.token_urlsafe(64)
    state_blob = _build_state(code_verifier, link_mode)
    challenge = _code_challenge(code_verifier)
    scope = _normalized_scope()

    params = {
        "response_type": "code",
        "client_id": settings.TWITTER_OAUTH_CLIENT_ID,
        "redirect_uri": settings.TWITTER_OAUTH_REDIRECT_URL,
        "scope": scope,
        "state": state_blob,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = AUTH_URL + "?" + urlencode(params)
    if settings.TWITTER_OAUTH_DEBUG:
        print("[twitter-oauth] auth_url=", url)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)

@router.get("/auth/twitter/callback")
async def twitter_callback(
    request: Request,
    state: str,
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> Any:
    # Handle error query returned by Twitter (e.g., invalid_scope)
    if error:
        msg = f"Twitter OAuth error: {error}"
        if error_description:
            msg += f" ({error_description})"
        return HTMLResponse(f"<h1>{msg}</h1><p><a href='/auth/login'>Back to login</a></p>", status_code=400)

    parsed = _parse_state(state)
    if not parsed:
        return HTMLResponse("<h1>Invalid state</h1>", status_code=400)
    code_verifier = parsed["v"]
    link_mode = int(parsed.get("link") or 0)

    if not settings.TWITTER_OAUTH_CLIENT_ID or not settings.TWITTER_OAUTH_REDIRECT_URL:
        return HTMLResponse("<h1>Twitter OAuth not configured</h1>", status_code=500)

    if not code:
        return HTMLResponse("<h1>Missing authorization code</h1>", status_code=400)

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.TWITTER_OAUTH_CLIENT_ID,
        "redirect_uri": settings.TWITTER_OAUTH_REDIRECT_URL,
        "code": code,
        "code_verifier": code_verifier,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if settings.TWITTER_OAUTH_CLIENT_SECRET:
        basic_raw = f"{settings.TWITTER_OAUTH_CLIENT_ID}:{settings.TWITTER_OAUTH_CLIENT_SECRET}"
        basic_b64 = base64.b64encode(basic_raw.encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {basic_b64}"

    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(TOKEN_URL, data=data, headers=headers)
        if r.status_code != 200:
            if settings.TWITTER_OAUTH_DEBUG:
                print("[twitter-oauth] token error", r.status_code, r.text[:400])
                print("[twitter-oauth] sent headers keys:", list(headers.keys()))
            return HTMLResponse("<h1>Token exchange failed</h1>", status_code=400)
        token_payload = r.json()

    id_token_raw = token_payload.get("id_token")
    access_token = token_payload.get("access_token")

    if settings.TWITTER_OAUTH_DEBUG:
        safe_keys = [k for k in token_payload.keys() if k not in ("access_token","refresh_token","id_token")]
        print("[twitter-oauth] token_payload keys (safe):", safe_keys)
        print("[twitter-oauth] token scopes:", token_payload.get("scope"))

    sub = None
    name = None
    picture = None
    email = None

    if id_token_raw:
        parts = id_token_raw.split(".")
        if len(parts) >= 2:
            def _b64d(x: str) -> bytes:
                x += "=" * (-len(x) % 4)
                return base64.urlsafe_b64decode(x.encode("utf-8"))
            try:
                payload = json.loads(_b64d(parts[1]).decode("utf-8"))
                sub = payload.get("sub") or sub
                name = payload.get("name") or name
                picture = payload.get("picture") or picture
                email = payload.get("email") or email
            except Exception as e:
                if settings.TWITTER_OAUTH_DEBUG:
                    print("[twitter-oauth] id_token decode failed:", repr(e))

    if access_token and (not sub or not name or not picture):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                ur = await client.get(
                    ME_URL + "?user.fields=profile_image_url,name,username",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if ur.status_code == 200:
                    ui = ur.json() or {}
                    data = ui.get("data") or {}
                    sub = sub or data.get("id")
                    name = name or data.get("name") or data.get("username")
                    picture = picture or data.get("profile_image_url")
                else:
                    if settings.TWITTER_OAUTH_DEBUG:
                        print("[twitter-oauth] users/me error", ur.status_code, ur.text[:400])
        except Exception as e:
            if settings.TWITTER_OAUTH_DEBUG:
                print("[twitter-oauth] users/me fetch failed:", repr(e))

    if not sub:
        return HTMLResponse("<h1>Unable to retrieve Twitter user id</h1>", status_code=400)

    if not email and settings.TWITTER_ALLOW_PSEUDO_EMAIL:
        email = f"{sub}@{settings.PSEUDO_EMAIL_DOMAIN}"

    current = get_current_user(request) if link_mode == 1 else None

    user_uid = await process_twitter_identity(
        sub=sub,
        email=email,
        name=name,
        picture=picture,
        link_mode=link_mode,
        current_user_uid=(current["user_uid"] if current else None),
        allow_pseudo_email=settings.TWITTER_ALLOW_PSEUDO_EMAIL,
        pseudo_domain=settings.PSEUDO_EMAIL_DOMAIN,
    )

    redirect = RedirectResponse("/", status_code=302)
    if current and link_mode == 1:
        redirect.set_cookie("yt_authp", "twitter", httponly=True, secure=True, samesite="lax",
                            max_age=60 * 60 * 24 * 30)
    else:
        create_session_cookie(redirect, user_uid)
        redirect.set_cookie("yt_authp", "twitter", httponly=True, secure=True, samesite="lax",
                            max_age=60 * 60 * 24 * 30)
    if name:
        redirect.set_cookie("yt_gname", quote_plus(name, safe='()'), httponly=False, secure=True, samesite="lax",
                            max_age=60 * 60 * 24 * 30)
    if picture:
        redirect.set_cookie("yt_gpic", picture, httponly=False, secure=True, samesite="lax",
                            max_age=60 * 60 * 24 * 30)
    return redirect