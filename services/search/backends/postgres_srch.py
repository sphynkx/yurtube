import math
from typing import Any, Dict, List, Tuple

from db import get_conn, release_conn
from services.search.settings_srch import settings


def _norm_query(q: str) -> str:
    return (q or "").strip()


class PostgresBackend:
    """
    PostgreSQL search backend:
      - FTS over title_norm + description_norm with custom TS config (settings.PG_TS_CONFIG, default 'yt_multi')
      - Author search via username (ILIKE + trigram index)
      - Fuzzy via pg_trgm on fuzzy-normalized fields (title_fuzzy/description_fuzzy):
          * word_similarity (in-text) with configurable threshold
          * % operator (threshold via set_limit)
          * ILIKE fallback
      - IMPORTANT: the query string is normalized to qf with the same rules as *_fuzzy fields
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
            # per-session trigram threshold for % operator
            try:
                await conn.execute("SELECT set_limit($1)", self.trgm_threshold)
            except Exception:
                pass

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
                # NOTE: qf is the query normalized with the same rules as *_fuzzy fields
                rows = await conn.fetch(
                    f"""
                    WITH params AS (
                      SELECT
                        websearch_to_tsquery('{self.ts_config}', $1) AS qt,
                        -- qf = lower( replace(replace( translate($1, 'ЁёЭэ' -> 'ЕеЕе'), 'эй'->'ей'), 'йо'->'ио') )
                        lower(
                          replace(
                            replace(
                              translate(
                                $1,
                                U&'\\0401\\0451\\042D\\044D',  -- Ё ё Э э
                                U&'\\0415\\0435\\0415\\0435'   -- Е е Е е
                              ),
                              U&'\\044D\\0439',                -- 'эй'
                              U&'\\0435\\0439'                 -- 'ей'
                            ),
                            U&'\\0439\\043E',                  -- 'йо'
                            U&'\\0438\\043E'                   -- 'ио'
                          )
                        ) AS qf
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
                      ts_rank_cd(
                        to_tsvector('{self.ts_config}', coalesce(v.title_norm,'') || ' ' || coalesce(v.description_norm,'')),
                        (SELECT qt FROM params)
                      ) AS fts_rank,
                      GREATEST(
                        word_similarity(v.title_fuzzy, (SELECT qf FROM params)),
                        word_similarity(v.description_fuzzy, (SELECT qf FROM params))
                      ) AS wsim,
                      GREATEST(
                        similarity(v.title_fuzzy, (SELECT qf FROM params)),
                        similarity(v.description_fuzzy, (SELECT qf FROM params))
                      ) AS sim
                    FROM videos v
                    JOIN users u ON u.user_uid = v.author_uid
                    LEFT JOIN categories c ON c.category_id = v.category_id
                    WHERE v.status='public' AND (
                      -- FTS on normalized fields with custom config
                      to_tsvector('{self.ts_config}', coalesce(v.title_norm,'') || ' ' || coalesce(v.description_norm,'')) @@ (SELECT qt FROM params)
                      -- author fuzzy (username)
                      OR u.username ILIKE ('%' || $1 || '%')
                      -- fuzzy on fuzzy-normalized fields, comparing with normalized query qf
                      OR v.title_fuzzy % (SELECT qf FROM params)
                      OR v.description_fuzzy % (SELECT qf FROM params)
                      OR word_similarity(v.title_fuzzy, (SELECT qf FROM params)) >= $4
                      OR word_similarity(v.description_fuzzy, (SELECT qf FROM params)) >= $4
                      OR v.title_fuzzy ILIKE ('%' || (SELECT qf FROM params) || '%')
                      OR v.description_fuzzy ILIKE ('%' || (SELECT qf FROM params) || '%')
                    )
                    ORDER BY
                      fts_rank DESC,
                      wsim DESC,
                      sim DESC,
                      (log(1 + COALESCE(v.views_count,0) + 5*COALESCE(v.likes_count,0))) DESC,
                      v.created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    q,
                    limit,
                    offset,
                    self.trgm_threshold,
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
                WHERE v.status='public' AND v.title_fuzzy ILIKE ($1 || '%')
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