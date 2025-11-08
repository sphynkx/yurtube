from typing import Optional, Dict, Any, List

async def get_identity(conn, provider: str, subject: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT provider, subject, user_uid, email, display_name, picture_url, created_at
        FROM sso_identities
        WHERE provider = $1 AND subject = $2
        LIMIT 1
        """,
        provider, subject,
    )
    return dict(row) if row else None

async def create_identity(conn, provider: str, subject: str, user_uid: str,
                          email: Optional[str],
                          display_name: Optional[str],
                          picture_url: Optional[str]) -> None:
    await conn.execute(
        """
        INSERT INTO sso_identities (provider, subject, user_uid, email, display_name, picture_url)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (provider, subject) DO NOTHING
        """,
        provider, subject, user_uid, email, display_name, picture_url,
    )

async def update_identity_profile(conn, provider: str, subject: str,
                                  display_name: Optional[str],
                                  picture_url: Optional[str]) -> None:
    await conn.execute(
        """
        UPDATE sso_identities
        SET display_name = $3,
            picture_url = $4
        WHERE provider = $1 AND subject = $2
        """,
        provider, subject, display_name, picture_url,
    )

async def list_identities_for_user(conn, user_uid: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT provider, subject, email, display_name, picture_url, created_at
        FROM sso_identities
        WHERE user_uid = $1
        ORDER BY created_at DESC
        """,
        user_uid,
    )
    return [dict(r) for r in rows]