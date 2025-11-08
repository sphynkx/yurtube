import asyncpg
from typing import Dict, Any

from db import get_conn, release_conn
from db.users_db import get_user_by_uid
from db.user_assets_db import (
    delete_user_avatar as _delete_user_avatar,
    get_user_avatar_path as _get_user_avatar_path,
    upsert_user_avatar as _upsert_user_avatar,
)
from db.sso_db import list_identities_for_user as _list_identities_for_user

async def fetch_profile_data(user_uid: str) -> Dict[str, Any]:
    """
    Return dict with:
      - username: str
      - avatar_rel: Optional[str]
      - sso_list: List[Dict[str, Any]]
    """
    conn = await get_conn()
    try:
        db_user = await get_user_by_uid(conn, user_uid)
        username = (db_user or {}).get("username") or ""
        avatar_rel = await _get_user_avatar_path(conn, user_uid)
        sso_list = await _list_identities_for_user(conn, user_uid)
        return {"username": username, "avatar_rel": avatar_rel, "sso_list": sso_list}
    finally:
        await release_conn(conn)

async def save_user_avatar_path(user_uid: str, rel_path: str) -> None:
    conn = await get_conn()
    try:
        await _upsert_user_avatar(conn, user_uid, rel_path)
    finally:
        await release_conn(conn)

async def remove_user_avatar_record(user_uid: str) -> None:
    conn = await get_conn()
    try:
        await _delete_user_avatar(conn, user_uid)
    finally:
        await release_conn(conn)

async def unlink_google_identity_if_possible(user_uid: str) -> str:
    """
    Returns one of: "ok", "no_google", "need_password_before_unlink"
    """
    conn = await get_conn()
    try:
        ident = await conn.fetchrow(
            "SELECT subject FROM sso_identities WHERE provider='google' AND user_uid=$1 LIMIT 1",
            user_uid,
        )
        if not ident:
            return "no_google"

        row_pw = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE user_uid=$1",
            user_uid,
        )
        pwd_hash = row_pw["password_hash"] if row_pw else ""
        if not pwd_hash:
            return "need_password_before_unlink"

        await conn.execute(
            "DELETE FROM sso_identities WHERE provider='google' AND user_uid=$1",
            user_uid,
        )
        return "ok"
    finally:
        await release_conn(conn)