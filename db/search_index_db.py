from typing import Any, Dict, Optional


async def fetch_video_for_index(conn, video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a video and related author/category fields needed by search indexer.
    """
    row = await conn.fetchrow(
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
          c.name AS category
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN categories c ON c.category_id = v.category_id
        WHERE v.video_id = $1
        """,
        video_id,
    )
    return dict(row) if row else None