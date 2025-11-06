from typing import Any, Dict, List, Optional, Sequence


async def fetch_video_brief(conn, video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch minimal info about a video used as the context seed for recommendations.
    Fields: video_id, title, description, author_uid, username, channel_id, category_id, created_at, views_count, likes_count, status
    """
    row = await conn.fetchrow(
        """
        SELECT
          v.video_id, v.title, v.description, v.status,
          v.author_uid, v.category_id, v.created_at,
          v.views_count, v.likes_count,
          u.username, u.channel_id
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        WHERE v.video_id = $1
        """,
        video_id,
    )
    return dict(row) if row else None


async def list_category_public_recent(conn, category_id: str, exclude_video_id: str, limit: int) -> List[Dict[str, Any]]:
    """
    Public videos within the same category, ordered by recency.
    """
    rows = await conn.fetch(
        """
        SELECT v.video_id, v.title, v.description, v.created_at, v.views_count, v.likes_count,
               v.author_uid, u.username, u.channel_id, v.category_id
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        WHERE v.status = 'public'
          AND v.category_id = $1
          AND v.video_id <> $2
        ORDER BY v.created_at DESC
        LIMIT $3
        """,
        category_id,
        exclude_video_id,
        max(1, int(limit)),
    )
    return [dict(r) for r in rows]


async def list_recent_from_authors(conn, author_uids: Sequence[str], exclude_video_id: str, limit: int) -> List[Dict[str, Any]]:
    """
    Public recent videos from a set of authors (subscriptions).
    """
    if not author_uids:
        return []
    rows = await conn.fetch(
        """
        SELECT v.video_id, v.title, v.description, v.created_at, v.views_count, v.likes_count,
               v.author_uid, u.username, u.channel_id, v.category_id
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        WHERE v.status = 'public'
          AND v.video_id <> $2
          AND v.author_uid = ANY($1::text[])
        ORDER BY v.created_at DESC
        LIMIT $3
        """,
        list(author_uids),
        exclude_video_id,
        max(1, int(limit)),
    )
    return [dict(r) for r in rows]