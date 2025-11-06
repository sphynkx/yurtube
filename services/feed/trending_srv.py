import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import get_conn, release_conn
from utils.url_ut import build_storage_url


def _date_str(dt: Any) -> Optional[str]:
    if isinstance(dt, datetime.datetime):
        return dt.strftime("%Y-%m-%d")
    try:
        return str(dt) if dt is not None else None
    except Exception:
        return None


async def fetch_trending_page(limit: int, offset: int, days: int) -> Tuple[List[Dict[str, Any]], int]:
    """
    Trending by a strict recency window + exponential decay:

    - Window filter: ONLY videos created within the last `days` are considered.
      (days is clamped to [1..365])
    - Score within the window:
        score = (views_count + 5*likes_count) * exp(- age_sec / (days*86400))
      Smaller `days` => stronger age strafe => freshest and popular videos to top.
    - Order: score DESC, created_at DESC
    - Pagination: (items, total) where total = count of public videos in the window.
    """
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    days = max(1, min(int(days), 365))

    conn = await get_conn()
    try:
        # Total for `days`
        total_row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS cnt
            FROM videos v
            WHERE v.status = 'public'
              AND v.created_at > (now() - make_interval(days => $1::int))
            """,
            days,
        )
        total = int(total_row["cnt"]) if total_row and "cnt" in total_row else 0
        if total == 0:
            return [], 0

        # Main request: filter by `days` window, count age_sec and score with decay
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
              -- raw popularity
              (b.views_count_f + 5.0 * b.likes_count_f) AS raw_pop,
              -- time decay factor with user-selected days bucket
              EXP( - b.age_sec / ( ($3::int) * 86400.0 ) ) AS decay,
              -- final score
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
    finally:
        await release_conn(conn)

    items: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        items.append(
            {
                "video_id": d.get("video_id"),
                "title": d.get("title") or "",
                "description": d.get("description") or "",
                "author": (d.get("username") or "").strip() or (d.get("channel_id") or ""),
                "category": d.get("category") or "",
                "views_count": int(d.get("views_count") or 0),
                "likes_count": int(d.get("likes_count") or 0),
                "uploaded_at": _date_str(d.get("created_at")),
                "thumb_url": build_storage_url(d["thumb_asset_path"]) if d.get("thumb_asset_path") else None,
                "thumb_url_anim": build_storage_url(d["thumb_anim_asset_path"]) if d.get("thumb_anim_asset_path") else None,
                "avatar_url": build_storage_url(d["avatar_asset_path"]) if d.get("avatar_asset_path") else None,
                "score": float(d.get("score") or 0.0),
            }
        )
    return items, total


async def fetch_trending(limit: int = 12, days: int = 7) -> List[Dict[str, Any]]:
    items, _ = await fetch_trending_page(limit=limit, offset=0, days=days)
    return items


async def fetch_recent_public(limit: int = 12) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 50))

    conn = await get_conn()
    try:
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
    finally:
        await release_conn(conn)

    items: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        items.append(
            {
                "video_id": d.get("video_id"),
                "title": d.get("title") or "",
                "description": d.get("description") or "",
                "author": (d.get("username") or "").strip() or (d.get("channel_id") or ""),
                "category": d.get("category") or "",
                "views_count": int(d.get("views_count") or 0),
                "likes_count": int(d.get("likes_count") or 0),
                "uploaded_at": _date_str(d.get("created_at")),
                "thumb_url": build_storage_url(d["thumb_asset_path"]) if d.get("thumb_asset_path") else None,
                "thumb_url_anim": build_storage_url(d["thumb_anim_asset_path"]) if d.get("thumb_anim_asset_path") else None,
                "avatar_url": build_storage_url(d["avatar_asset_path"]) if d.get("avatar_asset_path") else None,
            }
        )
    return items