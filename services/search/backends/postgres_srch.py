import math
from typing import Any, Dict, List, Tuple

from db import get_conn, release_conn


def _norm_query(q: str) -> str:
    return (q or "").strip()


class PostgresBackend:
    """
    PostgreSQL search backend:
      - Full-text search over title and description (EN+RU)
      - Author search via username (trigram-accelerated ILIKE)
      - Ranking combines FTS rank, popularity, and recency tiebreaker
      - Suggest titles by prefix (ILIKE)
    """

    async def search_videos(self, q: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        q = _norm_query(q)
        limit = max(1, min(int(limit or 10), 50))
        offset = max(0, int(offset or 0))

        conn = await get_conn()
        try:
            if not q:
                rows = await conn.fetch(
                    """
                    SELECT v.video_id, v.title, v.description, u.username AS author,
                           c.name AS category, v.views_count AS views, v.likes_count AS likes,
                           EXTRACT(EPOCH FROM v.created_at)::bigint AS created_at
                    FROM videos v
                    JOIN users u ON u.user_uid = v.author_uid
                    LEFT JOIN categories c ON c.category_id = v.category_id
                    WHERE v.status='public'
                    ORDER BY v.created_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    WITH q AS (
                      SELECT
                        websearch_to_tsquery('simple', $1) AS qs,
                        websearch_to_tsquery('russian', $1) AS qr
                    )
                    SELECT
                      v.video_id,
                      v.title,
                      v.description,
                      u.username AS author,
                      c.name AS category,
                      v.views_count AS views,
                      v.likes_count AS likes,
                      EXTRACT(EPOCH FROM v.created_at)::bigint AS created_at,
                      GREATEST(
                        ts_rank_cd(
                          setweight(to_tsvector('simple', coalesce(v.title,'')), 'A') ||
                          setweight(to_tsvector('simple', coalesce(v.description,'')), 'B'),
                          (SELECT qs FROM q)
                        ),
                        ts_rank_cd(
                          setweight(to_tsvector('russian', coalesce(v.title,'')), 'A') ||
                          setweight(to_tsvector('russian', coalesce(v.description,'')), 'B'),
                          (SELECT qr FROM q)
                        )
                      ) AS fts_rank
                    FROM videos v
                    JOIN users u ON u.user_uid = v.author_uid
                    LEFT JOIN categories c ON c.category_id = v.category_id
                    WHERE v.status='public' AND (
                      to_tsvector('simple', coalesce(v.title,'') || ' ' || coalesce(v.description,'')) @@ (SELECT qs FROM q)
                      OR to_tsvector('russian', coalesce(v.title,'') || ' ' || coalesce(v.description,'')) @@ (SELECT qr FROM q)
                      OR u.username ILIKE ('%' || $1 || '%')
                    )
                    ORDER BY
                      fts_rank DESC,
                      (log(1 + COALESCE(v.views_count,0) + 5*COALESCE(v.likes_count,0))) DESC,
                      v.created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    q,
                    limit,
                    offset,
                )

            out: List[Dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "video_id": r["video_id"],
                        "title": r["title"] or "",
                        "description": r["description"] or "",
                        "author": r["author"] or "",
                        "category": r["category"] or "",
                        "views_count": int(r["views"] or 0),
                        "likes_count": int(r["likes"] or 0),
                        "created_at_unix": int(r["created_at"] or 0),
                    }
                )
            return out
        finally:
            await release_conn(conn)

    async def suggest_titles(self, prefix: str, limit: int = 10) -> List[Dict[str, Any]]:
        s = _norm_query(prefix)
        if not s:
            return []
        limit = max(1, min(int(limit or 10), 25))
        conn = await get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT v.video_id, v.title
                FROM videos v
                WHERE v.status='public' AND v.title ILIKE ($1 || '%')
                ORDER BY v.created_at DESC, v.views_count DESC
                LIMIT $2
                """,
                s,
                limit,
            )
            return [{"video_id": r["video_id"], "title": r["title"] or ""} for r in rows]
        finally:
            await release_conn(conn)

    async def index_video(self, video: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    async def delete_video(self, video_id: str) -> Tuple[bool, str]:
        return True, ""