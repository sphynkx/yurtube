from typing import Any


async def count_public_videos_in_window(conn, days: int) -> int:
    """
    Count public videos created within the last `days`.
    """
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS cnt
        FROM videos v
        WHERE v.status = 'public'
          AND v.created_at > (now() - make_interval(days => $1::int))
        """,
        days,
    )
    return int(row["cnt"]) if row and "cnt" in row else 0


async def fetch_trending_rows(conn, limit: int, offset: int, days: int):
    """
    Fetch trending rows within a strict `days` window with age-decayed score.
    """
    rows = await conn.fetch(
        """
        WITH base AS (
          SELECT
            v.video_id,
            v.title,
            v.description,
            v.status,
            v.created_at,
            COALESCE(v.views_count,0)::float8 AS views_count_f,
            COALESCE(v.likes_count,0)::float8 AS likes_count_f,
            u.username,
            u.channel_id,
            c.name AS category,
            EXTRACT(EPOCH FROM (now() - v.created_at)) AS age_sec
          FROM videos v
          JOIN users u ON u.user_uid = v.author_uid
          LEFT JOIN categories c ON c.category_id = v.category_id
          WHERE v.status = 'public'
            AND v.created_at > (now() - make_interval(days => $3::int))
        )
        SELECT
          b.video_id,
          b.title,
          b.description,
          b.status,
          b.created_at,
          b.views_count_f::bigint AS views_count,
          b.likes_count_f::bigint AS likes_count,
          b.username,
          b.channel_id,
          b.category,
          (b.views_count_f + 5.0 * b.likes_count_f) AS raw_pop,
          EXP( - b.age_sec / ( ($3::int) * 86400.0 ) ) AS decay,
          (b.views_count_f + 5.0 * b.likes_count_f) * EXP( - b.age_sec / ( ($3::int) * 86400.0 ) ) AS score,
          ua.path     AS avatar_asset_path,
          vthumb.path AS thumb_asset_path,
          vanim.path  AS thumb_anim_asset_path
        FROM base b
        LEFT JOIN LATERAL (
          SELECT path
          FROM user_assets
          WHERE user_uid = (SELECT u.user_uid FROM users u WHERE u.username = b.username OR u.channel_id = b.channel_id LIMIT 1)
            AND asset_type = 'avatar'
          LIMIT 1
        ) ua ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = b.video_id AND asset_type = 'thumbnail_default'
          LIMIT 1
        ) vthumb ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = b.video_id AND asset_type = 'thumbnail_anim'
          LIMIT 1
        ) vanim ON true
        ORDER BY score DESC, b.created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
        days,
    )
    return rows


async def fetch_recent_public_rows(conn, limit: int):
    """
    Fetch most recent public videos.
    """
    rows = await conn.fetch(
        """
        SELECT
          v.video_id,
          v.title,
          v.description,
          v.status,
          v.created_at,
          v.views_count,
          v.likes_count,
          u.username,
          u.channel_id,
          c.name AS category,
          ua.path     AS avatar_asset_path,
          vthumb.path AS thumb_asset_path,
          vanim.path  AS thumb_anim_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN categories c ON c.category_id = v.category_id
        LEFT JOIN LATERAL (
          SELECT path
          FROM user_assets
          WHERE user_uid = v.author_uid AND asset_type = 'avatar'
          LIMIT 1
        ) ua ON true
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
        WHERE v.status = 'public'
        ORDER BY v.created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return rows