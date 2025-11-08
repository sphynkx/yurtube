import base64
import json
import os
import secrets
import hashlib
from typing import Any, Dict, Optional
from urllib.parse import urlencode, quote_plus

import httpx
import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi import status

from db import get_conn, release_conn
from db.users_db import create_user
from db.sso_db import get_identity, create_identity, update_identity_profile
from db.username_db import generate_unique_username
from utils.username_ut import sanitize_username_base
from utils.security_ut import create_session_cookie
from utils.idgen_ut import gen_id

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URL = os.getenv("GOOGLE_OAUTH_REDIRECT_URL", "").strip()
GOOGLE_ALLOWED_DOMAINS = os.getenv("GOOGLE_ALLOWED_DOMAINS", "").strip()
GOOGLE_DEBUG = os.getenv("GOOGLE_OAUTH_DEBUG", "0") == "1"

router = APIRouter()


def _build_state(code_verifier: str) -> str:
    csrf = secrets.token_urlsafe(16)
    payload = {"v": code_verifier, "csrf": csrf}
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _parse_state(state: str) -> Optional[Dict[str, Any]]:
    try:
        padded = state + "=" * (-len(state) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        obj = json.loads(raw.decode("utf-8"))
        if isinstance(obj, dict) and "v" in obj and "csrf" in obj:
            return obj
    except Exception:
        return None
    return None


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


@router.get("/auth/google/start")
async def google_start() -> Any:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URL:
        return HTMLResponse("<h1>Google OAuth not configured</h1>", status_code=500)

    code_verifier = secrets.token_urlsafe(64)
    state_blob = _build_state(code_verifier)
    challenge = _code_challenge(code_verifier)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URL,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state_blob,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "consent select_account",
        "include_granted_scopes": "false",
        "access_type": "offline",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    if GOOGLE_DEBUG:
        print("[google-oauth] auth_url=", auth_url)
    return RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/google/callback")
async def google_callback(request: Request, state: str, code: str) -> Any:
    parsed = _parse_state(state)
    if not parsed:
        return HTMLResponse("<h1>Invalid state</h1>", status_code=400)
    code_verifier = parsed["v"]

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URL:
        return HTMLResponse("<h1>Google OAuth not configured</h1>", status_code=500)

    token_endpoint = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GOOGLE_REDIRECT_URL,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(token_endpoint, data=data)
        if r.status_code != 200:
            print("[google-oauth] token error", r.status_code, r.text[:400])
            return HTMLResponse("<h1>Token exchange failed</h1>", status_code=400)
        token_payload = r.json()

    id_token_raw = token_payload.get("id_token")
    access_token = token_payload.get("access_token")
    if not id_token_raw:
        return HTMLResponse("<h1>No id_token returned</h1>", status_code=400)

    parts = id_token_raw.split(".")
    if len(parts) < 2:
        return HTMLResponse("<h1>Malformed id_token</h1>", status_code=400)

    def _b64d(x: str) -> bytes:
        x += "=" * (-len(x) % 4)
        return base64.urlsafe_b64decode(x.encode("utf-8"))

    try:
        payload = json.loads(_b64d(parts[1]).decode("utf-8"))
    except Exception:
        return HTMLResponse("<h1>Cannot decode token payload</h1>", status_code=400)

    sub = payload.get("sub")
    email = payload.get("email")
    email_verified = payload.get("email_verified")
    name = payload.get("name")
    picture = payload.get("picture")

    if access_token:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                ur = await client.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if ur.status_code == 200:
                    ui = ur.json()
                    name = ui.get("name") or name
                    picture = ui.get("picture") or picture
        except Exception as e:
            if GOOGLE_DEBUG:
                print("[google-oauth] userinfo fetch failed:", repr(e))

    if not sub or not email:
        return HTMLResponse("<h1>Missing sub/email in token</h1>", status_code=400)
    if email_verified is False:
        return HTMLResponse("<h1>Email not verified</h1>", status_code=400)

    if GOOGLE_ALLOWED_DOMAINS:
        domains = [d.strip().lower() for d in GOOGLE_ALLOWED_DOMAINS.split(",") if d.strip()]
        host = email.split("@")[-1].lower()
        if domains and host not in domains:
            return HTMLResponse("<h1>Email domain not allowed</h1>", status_code=403)

    conn = await get_conn()
    try:
        ident = await get_identity(conn, "google", sub)
        if ident:
            # Identity exists: update and reuse user
            user_uid = ident["user_uid"]
            await update_identity_profile(conn, "google", sub, name, picture)
        else:
            # Always create NEW user (never merge by email)
            base_name = sanitize_username_base(name, email)
            safe_name = await generate_unique_username(conn, base_name)

            user_uid = gen_id(20)
            channel_id = gen_id(24)

            email_to_use = email
            try:
                await create_user(
                    conn=conn,
                    user_uid=user_uid,
                    channel_id=channel_id,
                    username=safe_name,
                    email=email_to_use,
                    password_hash="",
                )
            except asyncpg.UniqueViolationError:
                # Email conflict: create alias or fall back to None
                try:
                    local, domain = email.split("@", 1)
                    alias = f"{local}+g{sub[:6]}@{domain}"
                except Exception:
                    alias = None
                if alias:
                    try:
                        await create_user(
                            conn=conn,
                            user_uid=user_uid,
                            channel_id=channel_id,
                            username=safe_name,
                            email=alias,
                            password_hash="",
                        )
                    except asyncpg.UniqueViolationError:
                        safe_name = await generate_unique_username(conn, base_name + "-g")
                        await create_user(
                            conn=conn,
                            user_uid=user_uid,
                            channel_id=channel_id,
                            username=safe_name,
                            email=alias,
                            password_hash="",
                        )
                else:
                    try:
                        await create_user(
                            conn=conn,
                            user_uid=user_uid,
                            channel_id=channel_id,
                            username=safe_name,
                            email=None,
                            password_hash="",
                        )
                    except asyncpg.UniqueViolationError:
                        safe_name = await generate_unique_username(conn, base_name + "-g")
                        await create_user(
                            conn=conn,
                            user_uid=user_uid,
                            channel_id=channel_id,
                            username=safe_name,
                            email=None,
                            password_hash="",
                        )

            await create_identity(conn, "google", sub, user_uid, email, name, picture)
    finally:
        await release_conn(conn)

    redirect = RedirectResponse("/", status_code=302)
    create_session_cookie(redirect, user_uid)
    redirect.set_cookie("yt_authp", "google", httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    if name:
        redirect.set_cookie("yt_gname", quote_plus(name), httponly=False, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    if picture:
        redirect.set_cookie("yt_gpic", picture, httponly=False, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return redirect