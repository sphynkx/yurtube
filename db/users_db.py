from typing import Any, Dict, Optional

import asyncpg
from typing import Optional, Any, Dict

import asyncpg

from utils.security_ut import verify_password


async def get_user_by_username(conn: asyncpg.Connection, username: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        "SELECT * FROM users WHERE lower(username) = lower($1)",
        username,
    )


async def get_user_by_uid(conn: asyncpg.Connection, user_uid: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow("SELECT * FROM users WHERE user_uid = $1", user_uid)


async def create_user(
    conn: asyncpg.Connection,
    user_uid: str,
    channel_id: str,
    username: str,
    email: str,
    password_hash: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO users (user_uid, channel_id, username, email, password_hash)
        VALUES ($1, $2, $3, $4, $5)
        """,
        user_uid,
        channel_id,
        username,
        email,
        password_hash,
    )


async def authenticate_user(conn: asyncpg.Connection, username: str, password: str) -> Optional[asyncpg.Record]:
    user = await get_user_by_username(conn, username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


async def get_user_by_name_or_channel(conn: asyncpg.Connection, name_or_channel: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user by @username or channel_id with avatar asset path.
    """
    row = await conn.fetchrow(
        """
        SELECT u.user_uid, u.username, u.channel_id, u.created_at,
               ua.path AS avatar_asset_path
        FROM users u
        LEFT JOIN user_assets ua
          ON ua.user_uid = u.user_uid AND ua.asset_type = 'avatar'
        WHERE lower(u.username) = lower($1) OR u.channel_id = $1
        LIMIT 1
        """,
        name_or_channel,
    )
    return dict(row) if row else None
from utils.security_ut import verify_password


async def get_user_by_username(conn: asyncpg.Connection, username: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        "SELECT * FROM users WHERE lower(username) = lower($1)",
        username,
    )


async def get_user_by_uid(conn: asyncpg.Connection, user_uid: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow("SELECT * FROM users WHERE user_uid = $1", user_uid)


async def create_user(
    conn: asyncpg.Connection,
    user_uid: str,
    channel_id: str,
    username: str,
    email: str,
    password_hash: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO users (user_uid, channel_id, username, email, password_hash)
        VALUES ($1, $2, $3, $4, $5)
        """,
        user_uid,
        channel_id,
        username,
        email,
        password_hash,
    )


async def authenticate_user(conn: asyncpg.Connection, username: str, password: str) -> Optional[asyncpg.Record]:
    user = await get_user_by_username(conn, username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


async def get_user_by_name_or_channel(conn, name_or_channel: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user by @username or channel_id with avatar asset path.
    """
    row = await conn.fetchrow(
        """
        SELECT u.user_uid, u.username, u.channel_id, u.created_at,
               ua.path AS avatar_asset_path
        FROM users u
        LEFT JOIN user_assets ua
          ON ua.user_uid = u.user_uid AND ua.asset_type = 'avatar'
        WHERE lower(u.username) = lower($1) OR u.channel_id = $1
        LIMIT 1
        """,
        name_or_channel,
    )
    return dict(row) if row else None