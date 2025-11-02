from typing import Any, Dict, List

from db import get_conn, release_conn

class PostgresBackend:
    def __init__(self) -> None:
        pass

    async def search_videos(self, q: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        sql = """
        WITH q AS (
          SELECT websearch_to_tsquery($1) AS tsq, $1::text AS rawq
        )
        SELECT
          v.video_id,
          v.title,
          v.description,
          u.username AS author,
          c.name AS category,
          v.views_count,
          v.likes_count,
          EXTRACT(EPOCH FROM v.created_at)::bigint AS created_at_unix,
          ts_rank_cd(v.search_vec, q.tsq, 1) AS rank_ts,
          similarity(v.title, q.rawq) AS rank_sim
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN categories c ON c.category_id = v.category_id,
        q
        WHERE
          v.status = 'public'
          AND (
            v.search_vec @@ q.tsq
            OR (q.rawq <> '' AND v.title % q.rawq)
          )
        ORDER BY
          (ts_rank_cd(v.search_vec, q.tsq, 1) * 1.0)
          + (similarity(v.title, q.rawq) * 0.7)
          + (LEAST(EXTRACT(EPOCH FROM (NOW() - v.created_at)) / 86400.0, 365.0) * -0.001)
          + (LN(GREATEST(v.views_count,1)) * 0.05) DESC
        LIMIT $2 OFFSET $3
        """
        conn = await get_conn()
        try:
            rows = await conn.fetch(sql, q, limit, offset)
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                out.append(
                    {
                        "video_id": d.get("video_id"),
                        "title": d.get("title", ""),
                        "description": d.get("description", ""),
                        "author": d.get("author", ""),
                        "category": d.get("category", ""),
                        "views_count": d.get("views_count", 0),
                        "likes_count": d.get("likes_count", 0),
                        "created_at_unix": int(d.get("created_at_unix", 0)),
                    }
                )
            return out
        finally:
            await release_conn(conn)

    async def suggest_titles(self, prefix: str, limit: int = 10) -> List[Dict[str, Any]]:
        sql = """
        SELECT video_id, title
        FROM videos
        WHERE status = 'public' AND title ILIKE $1 || '%'
        ORDER BY similarity(title, $1) DESC
        LIMIT $2
        """
        conn = await get_conn()
        try:
            rows = await conn.fetch(sql, prefix, limit)
            return [{"video_id": r["video_id"], "title": r["title"]} for r in rows]
        finally:
            await release_conn(conn)

    async def index_video(self, video: Dict[str, Any]) -> None:
        return

    async def delete_video(self, video_id: str) -> None:
        return