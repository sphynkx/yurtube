from typing import List

import asyncpg

from utils.idgen_ut import gen_id


async def is_subscribed(conn: asyncpg.Connection, subscriber_uid: str, channel_uid: str) -> bool:
    row = await conn.fetchrow(
        """
        SELECT 1
        FROM subscriptions
        WHERE subscriber_uid = $1 AND channel_uid = $2
        """,
        subscriber_uid,
        channel_uid,
    )
    return row is not None


async def subscribe(conn: asyncpg.Connection, subscriber_uid: str, channel_uid: str) -> None:
    if subscriber_uid == channel_uid:
        return
    if await is_subscribed(conn, subscriber_uid, channel_uid):
        return
    await conn.execute(
        """
        INSERT INTO subscriptions (subscription_uid, subscriber_uid, channel_uid)
        VALUES ($1, $2, $3)
        """,
        gen_id(20),
        subscriber_uid,
        channel_uid,
    )


async def unsubscribe(conn: asyncpg.Connection, subscriber_uid: str, channel_uid: str) -> None:
    await conn.execute(
        """
        DELETE FROM subscriptions
        WHERE subscriber_uid = $1 AND channel_uid = $2
        """,
        subscriber_uid,
        channel_uid,
    )


async def count_subscribers(conn: asyncpg.Connection, channel_uid: str) -> int:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS cnt
        FROM subscriptions
        WHERE channel_uid = $1
        """,
        channel_uid,
    )
    return int(row["cnt"]) if row else 0


async def list_subscribers(conn: asyncpg.Connection, channel_uid: str) -> List[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT u.user_uid, u.username, u.channel_id, u.created_at
        FROM subscriptions s
        JOIN users u ON u.user_uid = s.subscriber_uid
        WHERE s.channel_uid = $1
        ORDER BY s.created_at DESC
        """,
        channel_uid,
    )


async def list_subscriptions(conn: asyncpg.Connection, subscriber_uid: str) -> List[asyncpg.Record]:
    """
    Channels that the user is subscribed to.
    Includes channel avatar.
    """
    return await conn.fetch(
        """
        SELECT u.user_uid, u.username, u.channel_id, u.created_at,
               ua.path AS avatar_asset_path
        FROM subscriptions s
        JOIN users u ON u.user_uid = s.channel_uid
        LEFT JOIN user_assets ua
          ON ua.user_uid = u.user_uid AND ua.asset_type = 'avatar'
        WHERE s.subscriber_uid = $1
        ORDER BY s.created_at DESC
        """,
        subscriber_uid,
    )