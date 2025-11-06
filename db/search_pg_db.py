from typing import Any, Dict, List

async def _set_trgm_limit(conn, threshold: float) -> None:
    """
    Try to set per-session pg_trgm threshold (best-effort).
    """
    try:
        await conn.execute("SELECT set_limit($1)", float(threshold))
    except Exception:
        pass

async def pg_search_videos(conn, q: str, limit: int, offset: int, ts_config: str, trgm_threshold: float) -> List[Dict[str, Any]]:
    """
    Execute search. Returns list of dict rows:
    video_id, title, description, author, category, views, likes, created_at.
    """
    await _set_trgm_limit(conn, trgm_threshold)

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
        return [dict(r) for r in rows]

    sql = f"""
    WITH params AS (
      SELECT
        websearch_to_tsquery('{ts_config}', $1) AS qt,
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
        to_tsvector('{ts_config}', coalesce(v.title_norm,'') || ' ' || coalesce(v.description_norm,'')),
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
      to_tsvector('{ts_config}', coalesce(v.title_norm,'') || ' ' || coalesce(v.description_norm,'')) @@ (SELECT qt FROM params)
      OR u.username ILIKE ('%' || $1 || '%')
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
    """
    rows = await conn.fetch(sql, q, limit, offset, trgm_threshold)
    return [dict(r) for r in rows]

async def pg_suggest_titles(conn, prefix: str, limit: int) -> List[Dict[str, Any]]:
    """
    Suggest titles by prefix using fuzzy-normalized title field.
    """
    rows = await conn.fetch(
        """
        SELECT v.video_id, v.title
        FROM videos v
        WHERE v.status='public' AND v.title_fuzzy ILIKE ($1 || '%')
        ORDER BY v.created_at DESC, v.views_count DESC
        LIMIT $2
        """,
        prefix,
        limit,
    )
    return [dict(r) for r in rows]