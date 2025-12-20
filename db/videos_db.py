from typing import Any, List, Optional
import asyncpg


async def create_video(
    conn: asyncpg.Connection,
    video_id: str,
    author_uid: str,
    title: str,
    description: str,
    status: str,
    storage_path: str,
    category_id: Optional[str],
    is_age_restricted: bool,
    is_made_for_kids: bool,
) -> None:
    await conn.execute(
        """
        INSERT INTO videos (
          video_id, author_uid, title, description, duration_sec, status,
          processing_status, storage_path, category_id, is_age_restricted, is_made_for_kids
        )
        VALUES ($1,$2,$3,$4,0,$5,'uploaded',$6,$7,$8,$9)
        """,
        video_id,
        author_uid,
        title,
        description,
        status,
        storage_path,
        category_id,
        is_age_restricted,
        is_made_for_kids,
    )


async def set_video_ready(
    conn: asyncpg.Connection,
    video_id: str,
    duration_sec: Optional[int],
) -> None:
    if duration_sec is None:
        await conn.execute(
            """
            UPDATE videos
            SET processing_status = 'ready'
            WHERE video_id = $1
            """,
            video_id,
        )
    else:
        await conn.execute(
            """
            UPDATE videos
            SET processing_status = 'ready', duration_sec = $2
            WHERE video_id = $1
            """,
            video_id,
            duration_sec,
        )


async def list_latest_public_videos_count(conn) -> int:
    """
    Amount of public videos - for pagination on root page
    """
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS cnt
        FROM videos
        WHERE status = 'public'
          AND processing_status = 'ready'
        """
    )
    return int(row["cnt"] if row and row["cnt"] is not None else 0)


async def list_latest_public_videos(conn, limit: int = 24, offset: int = 0):
    """
    returns list of public videos sorted by date desc., with pagination.
    """
    rows = await conn.fetch(
        """
        SELECT v.video_id,
               v.title,
               v.duration_sec,
               v.storage_path,
               v.created_at,
               v.thumb_pref_offset AS thumb_pref_offset,
               vthumb.path AS thumb_asset_path,
               vanim.path  AS thumb_anim_asset_path,
               u.username,
               u.channel_id,
               uava.path   AS avatar_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_default'
          LIMIT 1
        ) vthumb ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_anim'
          LIMIT 1
        ) vanim ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM user_assets
          WHERE user_uid = v.author_uid AND asset_type = 'avatar'
          LIMIT 1
        ) uava ON true
        WHERE v.status = 'public'
          AND v.processing_status = 'ready'
        ORDER BY v.created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return rows


async def list_trending_public_videos(
    conn: asyncpg.Connection,
    period: str,
    limit: int,
    offset: int,
):
    if period == "day":
        interval = "1 day"
    elif period == "week":
        interval = "7 days"
    else:
        interval = "30 days"

    return await conn.fetch(
        f"""
        SELECT v.*, u.username, u.channel_id,
               a.path AS thumb_asset_path,
               ua.path AS avatar_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN categories vcat ON vcat.category_id = v.category_id
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_default'
          LIMIT 1
        ) vthumb ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_anim'
          LIMIT 1
        ) vanim ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM user_assets
          WHERE user_uid = v.author_uid AND asset_type = 'avatar'
          LIMIT 1
        ) uava ON true
        WHERE v.status = 'public'
          AND v.processing_status = 'ready'
          AND v.created_at >= NOW() - INTERVAL '{interval}'
        ORDER BY v.views_count DESC, v.created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )


async def list_subscription_feed(
    conn: asyncpg.Connection,
    subscriber_uid: str,
    limit: int,
    offset: int,
):
    return await conn.fetch(
        """
        SELECT v.*, u.username, u.channel_id,
               a.path AS thumb_asset_path,
               ua.path AS avatar_asset_path
        FROM subscriptions s
        JOIN videos v ON v.author_uid = s.channel_uid
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        WHERE s.subscriber_uid = $1
          AND v.status = 'public'
          AND v.processing_status = 'ready'
        ORDER BY v.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        subscriber_uid,
        limit,
        offset,
    )


async def list_history_distinct_latest(
    conn: asyncpg.Connection,
    user_uid: str,
    limit: int,
    offset: int,
):
    return await conn.fetch(
        """
        WITH last_view AS (
          SELECT video_id, MAX(watched_at) AS last_watched_at
          FROM views
          WHERE user_uid = $1
          GROUP BY video_id
        )
        SELECT v.*, u.username, u.channel_id,
               a.path AS thumb_asset_path,
               ua.path AS avatar_asset_path,
               lv.last_watched_at
        FROM last_view lv
        JOIN videos v ON v.video_id = lv.video_id
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        ORDER BY lv.last_watched_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_uid,
        limit,
        offset,
    )


async def list_author_public_videos(
    conn: asyncpg.Connection,
    author_uid: str,
    limit: int,
    offset: int,
):
    return await conn.fetch(
        """
        SELECT v.video_id,
               v.title,
               v.duration_sec,
               v.storage_path,
               v.created_at,
               v.thumb_pref_offset AS thumb_pref_offset,
               vthumb.path AS thumb_asset_path,
               vanim.path  AS thumb_anim_asset_path,
               u.username,
               u.channel_id,
               uava.path   AS avatar_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_default'
          LIMIT 1
        ) vthumb ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_anim'
          LIMIT 1
        ) vanim ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM user_assets
          WHERE user_uid = v.author_uid AND asset_type = 'avatar'
          LIMIT 1
        ) uava ON true
        WHERE v.author_uid = $1
          AND v.status = 'public'
          AND v.processing_status = 'ready'
        ORDER BY v.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        author_uid,
        limit,
        offset,
    )


async def get_video(
    conn: asyncpg.Connection,
    video_id: str,
):
    return await conn.fetchrow(
        """
        SELECT v.*, u.username, u.channel_id,
               ua.path AS avatar_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        WHERE v.video_id = $1
        """,
        video_id,
    )


async def list_my_videos(
    conn: asyncpg.Connection,
    author_uid: str,
    limit: int = 100,
):
    return await conn.fetch(
        """
        SELECT v.*, a.path AS thumb_asset_path
        FROM videos v
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        WHERE v.author_uid = $1
        ORDER BY v.created_at DESC
        LIMIT $2
        """,
        author_uid,
        limit,
    )


async def get_owned_video(
    conn: asyncpg.Connection,
    video_id: str,
    owner_uid: str,
):
    return await conn.fetchrow(
        """
        SELECT video_id, author_uid, storage_path
        FROM videos
        WHERE video_id = $1 AND author_uid = $2
        """,
        video_id,
        owner_uid,
    )


async def delete_video(
    conn: asyncpg.Connection,
    video_id: str,
    owner_uid: str,
) -> bool:
    """
    Delete a video row (owned by owner_uid).
    NOTE: best-effort cleanup of external resources (comments, files, search index)
    MUST be done by the caller in background to avoid blocking this call.
    """
    owned = await get_owned_video(conn, video_id, owner_uid)
    if not owned:
        return False

    res = await conn.execute(
        """
        DELETE FROM videos
        WHERE video_id = $1 AND author_uid = $2
        """,
        video_id,
        owner_uid,
    )
    return res.endswith("1")


async def get_video_min(
    conn,
    video_id: str,
):
    return await conn.fetchrow(
        "SELECT video_id, title FROM videos WHERE video_id = $1",
        video_id,
    )


async def delete_video_by_owner(conn: Any, video_id: str, author_uid: str) -> str:
    """
    Moved from routes/upload_rout.py manage_delete()
    Remove record if owner is same as..
    Return result string from driver (for example: 'DELETE 1' for asyncpg).
    """
    return await conn.execute(
        """
        DELETE FROM videos
        WHERE video_id = $1 AND author_uid = $2
        """,
        video_id,
        author_uid,
    )

async def count_history_distinct_latest(conn: asyncpg.Connection, user_uid: str) -> int:
    """
    Counts the total number of distinct videos in user's history.
    """
    result = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM (
          SELECT DISTINCT video_id
          FROM views
          WHERE user_uid = $1
        ) AS distinct_views
        """,
        user_uid,
    )
    return result


async def list_history_distinct_latest(
    conn: asyncpg.Connection,
    user_uid: str,
    limit: int,
    offset: int,
):
    return await conn.fetch(
        """
        WITH last_view AS (
          SELECT video_id, MAX(watched_at) AS last_watched_at
          FROM views
          WHERE user_uid = $1
          GROUP BY video_id
        )
        SELECT v.*, u.username, u.channel_id,
               a.path AS thumb_asset_path,
               ua.path AS avatar_asset_path,
               lv.last_watched_at
        FROM last_view lv
        JOIN videos v ON v.video_id = lv.video_id
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        ORDER BY lv.last_watched_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_uid,
        limit,
        offset,
    )