from typing import List, Optional, Dict, Any
import asyncpg
from datetime import datetime

# Insert notification; dedupe_key optional (for batch likes)
async def insert_notification(
    conn: asyncpg.Connection,
    user_uid: str,
    notif_type: str,
    payload: Dict[str, Any],
    agg_key: Optional[str] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[str]:
    sql = """
    INSERT INTO notifications (user_uid, type, payload, agg_key, dedupe_key)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (dedupe_key) DO NOTHING
    RETURNING notif_id
    """
    row = await conn.fetchrow(sql, user_uid, notif_type, payload, agg_key, dedupe_key)
    return row["notif_id"] if row else None

async def list_notifications(
    conn: asyncpg.Connection,
    user_uid: str,
    limit: int,
    offset: int,
) -> List[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT * FROM notifications
        WHERE user_uid = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_uid,
        limit,
        offset,
    )

async def mark_read(conn: asyncpg.Connection, user_uid: str, ids: List[str]) -> int:
    if not ids:
        return 0
    res = await conn.execute(
        """
        UPDATE notifications
        SET read_at = NOW()
        WHERE user_uid = $1 AND notif_id = ANY($2::uuid[])
        AND read_at IS NULL
        """,
        user_uid,
        ids,
    )
    return int(res.split()[-1])

async def mark_all_read(conn: asyncpg.Connection, user_uid: str) -> int:
    res = await conn.execute(
        """
        UPDATE notifications
        SET read_at = NOW()
        WHERE user_uid = $1 AND read_at IS NULL
        """,
        user_uid,
    )
    return int(res.split()[-1])

async def unread_count(conn: asyncpg.Connection, user_uid: str) -> int:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_uid = $1 AND read_at IS NULL",
        user_uid,
    )
    return int(row["cnt"] if row and row["cnt"] is not None else 0)

async def get_user_prefs(conn: asyncpg.Connection, user_uid: str) -> Dict[str, Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT type, inapp, email, allow_unlisted
        FROM user_notification_prefs
        WHERE user_uid = $1
        """,
        user_uid,
    )
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        out[r["type"]] = {
            "inapp": bool(r["inapp"]),
            "email": bool(r["email"]),
            "allow_unlisted": r["allow_unlisted"] if r["allow_unlisted"] is not None else None,
        }
    return out

async def set_user_prefs(
    conn: asyncpg.Connection,
    user_uid: str,
    prefs: List[Dict[str, Any]],
):
    for p in prefs:
        ptype = str(p.get("type") or "").strip()
        if not ptype:
            continue
        inapp = bool(p.get("inapp"))
        email = bool(p.get("email"))
        allow_unlisted = p.get("allow_unlisted")
        await conn.execute(
            """
            INSERT INTO user_notification_prefs (user_uid, type, inapp, email, allow_unlisted)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_uid, type) DO UPDATE
            SET inapp = EXCLUDED.inapp,
                email = EXCLUDED.email,
                allow_unlisted = EXCLUDED.allow_unlisted
            """,
            user_uid,
            ptype,
            inapp,
            email,
            allow_unlisted,
        )