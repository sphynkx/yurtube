import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from services.search.settings_srch import settings
from db.search_manticore_db import (
    http_sql_select_raw,
    http_sql_select,
    http_sql_raw_post,
    run_cli,
)

log = logging.getLogger(__name__)


def _docid_from_video_id(video_id: str) -> int:
    h = hashlib.blake2b(video_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, byteorder="big", signed=False)


def _esc_sql_str(val: str) -> str:
    s = str(val)
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return s


def _extract_column_names(columns: Any) -> List[Optional[str]]:
    names: List[Optional[str]] = []
    if isinstance(columns, list):
        for it in columns:
            if isinstance(it, dict):
                if "name" in it and isinstance(it["name"], str):
                    names.append(it["name"])
                elif len(it) == 1:
                    names.append(next(iter(it.keys())))
                else:
                    names.append(None)
            elif isinstance(it, str):
                names.append(it)
            else:
                names.append(None)
    return names


def _rows_from_result_obj(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = obj.get("data", [])
    if not data:
        return []
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data
    cols = _extract_column_names(obj.get("columns"))
    out: List[Dict[str, Any]] = []
    for row in data:
        if isinstance(row, list):
            item: Dict[str, Any] = {}
            for i, val in enumerate(row):
                key = cols[i] if i < len(cols) and cols[i] else f"c{i}"
                item[key] = val
            out.append(item)
    return out


def _rows_from_hits_obj(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = obj.get("hits")
    if not isinstance(hits, dict):
        return []
    arr = hits.get("hits")
    if not isinstance(arr, list):
        return []
    out: List[Dict[str, Any]] = []
    for h in arr:
        if isinstance(h, dict):
            src = h.get("_source")
            if isinstance(src, dict):
                out.append(src)
    return out


def _normalize_rows(res: Union[Dict[str, Any], List[Any]]) -> List[Dict[str, Any]]:
    if isinstance(res, dict):
        if "hits" in res:
            rows = _rows_from_hits_obj(res)
            if rows:
                return rows
        if "data" in res or "columns" in res:
            return _rows_from_result_obj(res)
        return []
    if isinstance(res, list):
        for item in res:
            if isinstance(item, dict):
                if "hits" in item:
                    rows = _rows_from_hits_obj(item)
                    if rows:
                        return rows
                if "data" in item or "columns" in item:
                    rows = _rows_from_result_obj(item)
                    if rows:
                        return rows
        return []
    return []


def _run_select(sql: str) -> List[Dict[str, Any]]:
    if log.isEnabledFor(logging.DEBUG):
        log.debug("Manticore SELECT: %s", sql)
    # Graceful: protect network/JSON errors and return empty rows on failure
    try:
        res = http_sql_select(sql)
    except Exception as e:
        log.error("Manticore SELECT failed: %r", e)
        return []
    return _normalize_rows(res)


def _build_match_simple(q: str) -> str:
    # Keeping exact behavior as before, without localization tweaks in this layer.
    parts = [t for t in (q or "").strip().split() if t]
    return " ".join(parts) if parts else ""


def _build_match_advanced(q: str) -> str:
    # Using simple term ORs in fields, advanced form for multi-term queries.
    s = _build_match_simple(q)
    return f"@title {s} | @description {s} | @author {s}"


class ManticoreBackend:
    def __init__(self) -> None:
        self.index = settings.MANTICORE_INDEX_VIDEOS

    async def search_videos(self, q: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        q = (q or "").strip()
        rows: List[Dict[str, Any]] = []
        if q:
            parts = q.split()
            match_adv = _esc_sql_str(_build_match_advanced(q)) if len(parts) > 1 else None
            match_simple = _esc_sql_str(_build_match_simple(q))
            if match_adv:
                sql1 = (
                    f"SELECT id, video_id, title, description, author, category, views, likes, created_at, WEIGHT() AS w "
                    f"FROM {self.index} WHERE MATCH('{match_adv}') AND status='public' "
                    f"ORDER BY w DESC, created_at DESC LIMIT {int(limit)} OFFSET {int(offset)} "
                    f"OPTION ranker=bm25, field_weights=(title=6, description=2, author=3)"
                )
                rows = _run_select(sql1)
            if not rows:
                sql2 = (
                    f"SELECT id, video_id, title, description, author, category, views, likes, created_at, WEIGHT() AS w "
                    f"FROM {self.index} WHERE MATCH('{match_simple}') AND status='public' "
                    f"ORDER BY w DESC, created_at DESC LIMIT {int(limit)} OFFSET {int(offset)} "
                    f"OPTION ranker=bm25, field_weights=(title=6, description=2, author=3)"
                )
                rows = _run_select(sql2)
        else:
            sql = (
                f"SELECT id, video_id, title, description, author, category, views, likes, created_at, 0 AS w "
                f"FROM {self.index} WHERE status='public' "
                f"ORDER BY created_at DESC LIMIT {int(limit)} OFFSET {int(offset)}"
            )
            rows = _run_select(sql)
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "video_id": r.get("video_id"),
                    "title": r.get("title", ""),
                    "description": r.get("description", ""),
                    "author": r.get("author", ""),
                    "category": r.get("category", ""),
                    "views_count": r.get("views", 0),
                    "likes_count": r.get("likes", 0),
                    "created_at_unix": r.get("created_at", 0),
                }
            )
        return out

    async def suggest_titles(self, prefix: str, limit: int = 10) -> List[Dict[str, Any]]:
        s = (prefix or "").strip()
        if not s:
            return []
        match = _esc_sql_str(_build_match_simple(s))
        sql = (
            f"SELECT video_id, title, WEIGHT() AS w FROM {self.index} "
            f"WHERE MATCH('{match}') AND status='public' ORDER BY w DESC, created_at DESC LIMIT {int(limit)} "
            f"OPTION ranker=bm25, field_weights=(title=6, author=3)"
        )
        rows = _run_select(sql)
        return [{"video_id": r.get("video_id"), "title": r.get("title", "")} for r in rows]

    async def index_video(self, video: Dict[str, Any]) -> Tuple[bool, str]:
        vid = str(video["video_id"])
        docid = _docid_from_video_id(vid)
        title = _esc_sql_str(video.get("title", ""))
        desc = _esc_sql_str(video.get("description", ""))
        tags = video.get("tags", [])
        tags_s = _esc_sql_str(",".join(tags)) if isinstance(tags, list) else _esc_sql_str(str(tags or ""))
        author = _esc_sql_str(video.get("author", ""))
        category = _esc_sql_str(video.get("category", ""))
        status = _esc_sql_str(video.get("status", "public"))
        created_at = int(video.get("created_at_unix", 0))
        views = int(video.get("views_count", 0))
        likes = int(video.get("likes_count", 0))
        lang = _esc_sql_str(video.get("lang", ""))
        sql = (
            f"REPLACE INTO {self.index} "
            f"(id, video_id, title, description, tags, author, category, status, created_at, views, likes, lang) VALUES ("
            f"{docid}, '{vid}', '{title}', '{desc}', '{tags_s}', '{author}', '{category}', '{status}', "
            f"{created_at}, {views}, {likes}, '{lang}')"
        )
        if log.isEnabledFor(logging.DEBUG):
            log.debug("Manticore REPLACE (len=%d)", len(sql))
        ok, msg = http_sql_raw_post(sql)
        if ok:
            return True, ""
        ok2, msg2 = run_cli(sql)
        if not ok2:
            return False, f"http-post failed: {msg}; cli failed: {msg2}"
        return True, ""

    async def delete_video(self, video_id: str) -> Tuple[bool, str]:
        docid = _docid_from_video_id(video_id)
        sql = f"DELETE FROM {self.index} WHERE id={docid}"
        if log.isEnabledFor(logging.DEBUG):
            log.debug("Manticore DELETE: %s", sql)
        ok, msg = http_sql_raw_post(sql)
        if ok:
            return True, ""
        ok2, msg2 = run_cli(sql)
        if not ok2:
            return False, f"http-post failed: {msg}; cli failed: {msg2}"
        return True, ""