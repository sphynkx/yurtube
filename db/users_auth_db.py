from typing import Any, Dict, Optional

async def get_user_auth_by_uid(conn, user_uid: str) -> Optional[Dict[str, Any]]:
    """
    Return minimal auth info for a user. Assumes `users.password_hash` exists.
    Optionally you may later read password_changed_at if needed.
    """
    row = await conn.fetchrow(
        """
        SELECT user_uid, password_hash, password_changed_at
        FROM users
        WHERE user_uid = $1
        LIMIT 1
        """,
        user_uid,
    )
    return dict(row) if row else None

async def update_user_password_hash(conn, user_uid: str, password_hash: str) -> None:
    """
    Update password hash and bump password_changed_at.
    """
    await conn.execute(
        """
        UPDATE users
        SET password_hash = $2,
            password_changed_at = now()
        WHERE user_uid = $1
        """,
        user_uid,
        password_hash,
    )