import math
from typing import Any, Dict, List, Tuple

from db import get_conn, release_conn
from services.search.settings_srch import settings
from db.search_pg_db import (
    pg_search_videos,
    pg_suggest_titles,
)


def _norm_query(q: str) -> str:
    return (q or "").strip()


class PostgresBackend:
    """
    PostgreSQL search backend:
      - FTS over title_norm + description_norm with custom TS config (settings.PG_TS_CONFIG, default 'yt_multi')
      - Author search via username (ILIKE + trigram index)
      - Fuzzy via pg_trgm on fuzzy-normalized fields (title_fuzzy/description_fuzzy)
      - Ranking: FTS desc, then word-sim desc, then trigram sim desc, then popularity, then recency
    """

    def __init__(self) -> None:
        self.ts_config = getattr(settings, "PG_TS_CONFIG", "yt_multi")
        try:
            self.trgm_threshold = float(getattr(settings, "TRGM_THRESHOLD", "0.22"))
        except Exception:
            self.trgm_threshold = 0.22

    async def search_videos(self, q: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        q = _norm_query(q)
        limit = max(1, min(int(limit or 10), 50))
        offset = max(0, int(offset or 0))

        conn = await get_conn()
        try:
            rows = await pg_search_videos(
                conn,
                q=q,
                limit=limit,
                offset=offset,
                ts_config=self.ts_config,
                trgm_threshold=self.trgm_threshold,
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
            rows = await pg_suggest_titles(conn, s, limit)
            return [{"video_id": r["video_id"], "title": r["title"] or ""} for r in rows]
        finally:
            await release_conn(conn)

    async def index_video(self, video: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    async def delete_video(self, video_id: str) -> Tuple[bool, str]:
        return True, ""