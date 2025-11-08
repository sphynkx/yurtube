import asyncpg
from typing import Optional
from db import get_conn, release_conn
from db.sso_db import get_identity, create_identity, update_identity_profile
from db.users_db import create_user, get_user_by_email
from utils.idgen_ut import gen_id

# All DB operations for Google SSO callback are consolidated here.

async def _username_exists(conn: asyncpg.Connection, uname: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM users WHERE lower(username)=lower($1) LIMIT 1",
        uname,
    )
    return bool(row)

def _sanitize_base(name: str) -> str:
    # Save space as delimiter: replace it on "-" - beautication..
    name = name.strip()
    name = name.replace(" ", "-")
    allowed = []
    for ch in name:
        if ch.isalnum() or ch in "._-":
            allowed.append(ch)
    cleaned = "".join(allowed)
    if not cleaned:
        cleaned = "user"
    return cleaned[:30]

async def _gen_unique_username(conn: asyncpg.Connection, base: str) -> str:
    # If base is free - use it
    if not await _username_exists(conn, base):
        return base
    # Try suffixes -g1 .. -g9
    for i in range(1, 10):
        candidate = f"{base}-g{i}"
        if len(candidate) > 30:
            candidate = candidate[:30]
        if not await _username_exists(conn, candidate):
            return candidate
    # Move on to a random suffix
    for _ in range(20):
        cand = f"{base}-g{gen_id(4)}"
        if len(cand) > 30:
            cand = cand[:30]
        if not await _username_exists(conn, cand):
            return cand
    # Fallback
    return f"user-{gen_id(6)}"

async def process_google_identity(
    sub: str,
    email: str,
    email_verified: bool,
    name: Optional[str],
    picture: Optional[str],
    link_mode: int,
    current_user_uid: Optional[str],
    auto_link_google_by_email: bool,
) -> str:
    """
    Returns user_uid that should be logged in after Google OAuth callback.
    Handles:
      - existing identity (updates profile)
      - explicit linking (link_mode=1)
      - auto-link by verified email (if enabled)
      - new user creation
    """
    conn = await get_conn()
    try:
        ident = await get_identity(conn, "google", sub)
        if ident:
            user_uid = ident["user_uid"]
            await update_identity_profile(conn, "google", sub, name, picture)
            return user_uid

        if link_mode == 1 and current_user_uid:
            # Explicit linking: attach identity to current user
            await create_identity(conn, "google", sub, current_user_uid, email, name, picture)
            return current_user_uid

        if auto_link_google_by_email and email_verified:
            existing = await get_user_by_email(conn, email)
            if existing:
                user_uid = existing["user_uid"]
                await create_identity(conn, "google", sub, user_uid, email, name, picture)
                return user_uid

        # Create brand new user (no merge by email unless auto-link matched above)
        base_name = (name or email.split("@")[0] or "user").strip()
        safe_base = _sanitize_base(base_name)
        safe_name = await _gen_unique_username(conn, safe_base)

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
            # Try alias path
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
                    safe_name = await _gen_unique_username(conn, safe_base + "-g")
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
                    safe_name = await _gen_unique_username(conn, safe_base + "-g")
                    await create_user(
                        conn=conn,
                        user_uid=user_uid,
                        channel_id=channel_id,
                        username=safe_name,
                        email=None,
                        password_hash="",
                    )

        await create_identity(conn, "google", sub, user_uid, email, name, picture)
        return user_uid
    finally:
        await release_conn(conn)