import asyncpg
from typing import Optional
from db import get_conn, release_conn
from db.sso_db import get_identity, create_identity, update_identity_profile
from db.users_db import create_user
from db.username_db import generate_unique_username
from utils.username_ut import sanitize_username_base
from utils.idgen_ut import gen_id

# All DB operations for Twitter SSO callback are consolidated here.

async def process_twitter_identity(
    sub: str,
    email: Optional[str],
    name: Optional[str],
    picture: Optional[str],
    link_mode: int,
    current_user_uid: Optional[str],
    allow_pseudo_email: bool,
    pseudo_domain: str,
) -> str:
    """
    Returns user_uid that should be logged in after Twitter OAuth callback.
    Handles:
      - existing identity (update profile)
      - explicit linking (link_mode=1)
      - new user creation (with optional pseudo email)
    """
    conn = await get_conn()
    try:
        ident = await get_identity(conn, "twitter", sub)
        if ident:
            user_uid = ident["user_uid"]
            await update_identity_profile(conn, "twitter", sub, name, picture)
            return user_uid

        if link_mode == 1 and current_user_uid:
            # Explicit linking
            await create_identity(conn, "twitter", sub, current_user_uid, email, name, picture)
            return current_user_uid

        # New user
        pseudo_email = None
        if not email and allow_pseudo_email:
            pseudo_email = f"{sub}@{pseudo_domain}"

        base_name = sanitize_username_base(name, email or pseudo_email)
        safe_name = await generate_unique_username(conn, base_name)

        user_uid = gen_id(20)
        channel_id = gen_id(24)

        email_to_use = email or pseudo_email
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
            # Rare conflict -> fallback to None
            await create_user(
                conn=conn,
                user_uid=user_uid,
                channel_id=channel_id,
                username=safe_name,
                email=None,
                password_hash="",
            )

        await create_identity(conn, "twitter", sub, user_uid, email_to_use, name, picture)
        return user_uid
    finally:
        await release_conn(conn)