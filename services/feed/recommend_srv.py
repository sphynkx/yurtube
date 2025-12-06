## SRTG_2MODIFY: build_storage_url(
## SRTG_2MODIFY: _path
import math
import time
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Set

from config.config import settings
from db import get_conn, release_conn
from db.recommend_db import fetch_video_brief, list_category_public_recent, list_recent_from_authors
from db.videos_db import list_author_public_videos
from db.search_db import fetch_video_assets_by_ids
from db.subscriptions_db import list_subscriptions
from services.feed.trending_srv import fetch_trending
from services.search.search_client_srch import get_backend
from utils.url_ut import build_storage_url

# Right-bar recommendation logic:
# Sources of candidates:
# - Same author: other public videos by the same author (exclude current video).
# - Same category: public videos in the same category (recent).
# - Search-based: use search backend on current title to get text-similar videos.
# - Subscriptions (if user): recent public videos from channels the user follows.
# - Fallback: trending (recent window).
#
# Scoring components:
# - Popularity: P = log(1 + views + 5*likes)
# - Freshness decay: D = exp(-age_sec / (tau_days * 86400))
# - Text similarity: S in [0..1] (if backend provides rank/weight; otherwise 0)
# - Same author boost: A = 1.0 if same-author else 0.0
# - Same category boost: C = 1.0 if same-category else 0.0
#
# Final score (when S present):
#   score = 0.40*(P*D) + 0.35*S + 0.15*A + 0.10*C
# When S missing:
#   score = 0.75*(P*D) + 0.15*A + 0.10*C
#
# Diversification quotas (top-10 window):
# - Max same author: settings.RIGHTBAR_MAX_SAME_AUTHOR_TOP10 (default 3)
# - Max same category: settings.RIGHTBAR_MAX_SAME_CATEGORY_TOP10 (default 6)
#
# Deterministic jitter:
# - To vary ordering across different current videos/users without randomness,
#   add a tiny deterministic jitter to the final score based on (ctx_video_id, candidate_id, user_uid).
#   This produces different stable orders for different contexts.
#
# Notes:
# - Only status='public' are shown.
# - Current video is excluded always.
# - On errors the recommendation silently degrades to empty list or trending fallback.

def _now_unix() -> int:
    return int(time.time())


def _uploaded_at_str(dt: Any) -> Optional[str]:
    try:
        import datetime
        if isinstance(dt, datetime.datetime):
            return dt.strftime("%Y-%m-%d")
        if dt is not None:
            return str(dt)
    except Exception:
        pass
    return None


async def _search_candidates(title: str, limit: int) -> List[Dict[str, Any]]:
    backend = get_backend()
    rows = await backend.search_videos(title or "", limit, 0)
    return rows or []


def _popularity(views: int, likes: int) -> float:
    return math.log(1.0 + max(0, int(views)) + 5.0 * max(0, int(likes)))


def _decay(created_at_unix: int, tau_days: int) -> float:
    now = _now_unix()
    age_sec = max(0, now - int(created_at_unix))
    tau = max(1, tau_days) * 86400.0
    return math.exp(-age_sec / tau)


def _deterministic_jitter(ctx_video_id: str, candidate_id: str, user_uid: Optional[str]) -> float:
    """
    Very small stable jitter in [0..0.01) derived from (ctx_video_id, candidate_id, user_uid).
    This makes ordering differ across videos/users while being stable across reloads.
    """
    key = f"{ctx_video_id}|{candidate_id}|{user_uid or ''}"
    h = hashlib.blake2b(key.encode("utf-8"), digest_size=4).digest()
    n = int.from_bytes(h, byteorder="big", signed=False)
    return (n % 1000) / 1000.0 * 0.01  # 0.000 .. 0.009


def _score_item(d: Dict[str, Any], ctx: Dict[str, Any], tau_days: int, s_norm: float) -> float:
    views = int(d.get("views_count") or 0)
    likes = int(d.get("likes_count") or 0)
    created_ts = 0
    cu = d.get("created_at_unix")
    if cu is not None:
        try:
            created_ts = int(cu)
        except Exception:
            created_ts = 0
    if created_ts == 0 and d.get("created_at") is not None:
        try:
            import datetime
            if hasattr(d["created_at"], "timestamp"):
                created_ts = int(d["created_at"].timestamp())
        except Exception:
            created_ts = 0

    P = _popularity(views, likes)
    D = _decay(created_ts, tau_days)
    A = 1.0 if d.get("author_uid") and ctx.get("author_uid") and d["author_uid"] == ctx["author_uid"] else 0.0
    C = 1.0 if d.get("category_id") and ctx.get("category_id") and d["category_id"] == ctx["category_id"] else 0.0

    if s_norm > 0.0:
        return 0.40 * (P * D) + 0.35 * s_norm + 0.15 * A + 0.10 * C
    else:
        return 0.75 * (P * D) + 0.15 * A + 0.10 * C


def _apply_diversity(sorted_items: List[Dict[str, Any]], limit: int, max_same_author_top10: int, max_same_cat_top10: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    cnt_author: Dict[str, int] = {}
    cnt_cat: Dict[str, int] = {}
    for item in sorted_items:
        if len(out) >= limit:
            break
        au = str(item.get("author_uid") or "")
        ca = str(item.get("category_id") or "")
        pos = len(out)
        if pos < 10:
            if au and cnt_author.get(au, 0) >= max_same_author_top10:
                continue
            if ca and cnt_cat.get(ca, 0) >= max_same_cat_top10:
                continue
        out.append(item)
        if au:
            cnt_author[au] = cnt_author.get(au, 0) + 1
        if ca:
            cnt_cat[ca] = cnt_cat.get(ca, 0) + 1
    return out


async def fetch_rightbar_for_video(video_id: str, user_uid: Optional[str], limit: int = 12) -> List[Dict[str, Any]]:
    if not getattr(settings, "RIGHTBAR_ENABLED", True):
        return []

    limit = max(1, min(int(limit or 12), 24))
    tau_days = max(1, int(getattr(settings, "RIGHTBAR_TAU_DAYS", 7)))
    search_take = max(1, int(getattr(settings, "RIGHTBAR_SEARCH_TAKE", 50)))
    q_same_author = max(3, int(getattr(settings, "RIGHTBAR_MAX_SAME_AUTHOR_TOP10", 3)))
    q_same_cat = max(4, int(getattr(settings, "RIGHTBAR_MAX_SAME_CATEGORY_TOP10", 6)))

    conn = await get_conn()
    try:
        ctx = await fetch_video_brief(conn, video_id)
        if not ctx or ctx.get("status") != "public":
            fallback = await fetch_trending(limit=limit, days=tau_days)
            for it in fallback:
                it["uploaded_at"] = it.get("uploaded_at")
            return fallback

        ctx_author = ctx.get("author_uid")
        ctx_cat = ctx.get("category_id")

        seen: Set[str] = set([video_id])
        pool: Dict[str, Dict[str, Any]] = {}

        # Same author
        if ctx_author:
            rows = await list_author_public_videos(conn, ctx_author, limit=80, offset=0)
            for r in rows:
                d = dict(r)
                vid = d.get("video_id")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                pool[vid] = {
                    "video_id": vid,
                    "title": d.get("title") or "",
                    "description": d.get("description") or "",
                    "author_uid": d.get("author_uid"),
                    "username": d.get("username"),
                    "channel_id": d.get("channel_id"),
                    "category_id": d.get("category_id"),
                    "created_at": d.get("created_at"),
                    "views_count": int(d.get("views_count") or 0),
                    "likes_count": int(d.get("likes_count") or 0),
                    "_src_same_author": 1,
                }

        # Same category
        if ctx_cat:
            rows = await list_category_public_recent(conn, ctx_cat, video_id, limit=120)
            for d in rows:
                vid = d.get("video_id")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                pool[vid] = {
                    "video_id": vid,
                    "title": d.get("title") or "",
                    "description": d.get("description") or "",
                    "author_uid": d.get("author_uid"),
                    "username": d.get("username"),
                    "channel_id": d.get("channel_id"),
                    "category_id": d.get("category_id"),
                    "created_at": d.get("created_at"),
                    "views_count": int(d.get("views_count") or 0),
                    "likes_count": int(d.get("likes_count") or 0),
                    "_src_same_category": 1,
                }

        # Search-based
        try:
            srows = await _search_candidates(ctx.get("title") or "", search_take)
        except Exception:
            srows = []
        for d in srows:
            vid = d.get("video_id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            pool.setdefault(vid, {}).update(
                {
                    "video_id": vid,
                    "title": d.get("title") or pool.get(vid, {}).get("title") or "",
                    "description": d.get("description") or pool.get(vid, {}).get("description") or "",
                    "views_count": int(d.get("views_count") or 0),
                    "likes_count": int(d.get("likes_count") or 0),
                    "created_at_unix": int(d.get("created_at_unix") or 0),
                    "_src_search": 1,
                }
            )

        # Subscriptions
        if user_uid:
            try:
                subs = await list_subscriptions(conn, user_uid)
            except Exception:
                subs = []
            author_uids = [str(s["channel_uid"]) for s in subs if s.get("channel_uid")]
            if author_uids:
                srows = await list_recent_from_authors(conn, author_uids, video_id, limit=80)
                for d in srows:
                    vid = d.get("video_id")
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    pool[vid] = {
                        "video_id": vid,
                        "title": d.get("title") or "",
                        "description": d.get("description") or "",
                        "author_uid": d.get("author_uid"),
                        "username": d.get("username"),
                        "channel_id": d.get("channel_id"),
                        "category_id": d.get("category_id"),
                        "created_at": d.get("created_at"),
                        "views_count": int(d.get("views_count") or 0),
                        "likes_count": int(d.get("likes_count") or 0),
                        "_src_subs": 1,
                    }

        # Fallback trending enrichment into pool if still small
        if len(pool) < limit:
            tf = await fetch_trending(limit=limit * 3, days=tau_days)
            for d in tf:
                vid = d.get("video_id")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                pool[vid] = {
                    "video_id": vid,
                    "title": d.get("title") or "",
                    "description": d.get("description") or "",
                    "username": d.get("author") or "",
                    "category": d.get("category") or "",
                    "created_at_unix": 0,
                    "views_count": int(d.get("views_count") or 0),
                    "likes_count": int(d.get("likes_count") or 0),
                    "_src_trending": 1,
                }

        # Enrich assets
        ids = list(pool.keys())
        assets_rows = await fetch_video_assets_by_ids(conn, ids)
        by_id = {r["video_id"]: r for r in assets_rows}

    finally:
        await release_conn(conn)

    # Score + jitter, sort
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for vid, it in pool.items():
        # try to infer created_at_unix from assets row
        if not it.get("created_at_unix"):
            r = by_id.get(vid)
            if r and r.get("created_at") is not None:
                try:
                    import datetime
                    if hasattr(r["created_at"], "timestamp"):
                        it["created_at_unix"] = int(r["created_at"].timestamp())
                except Exception:
                    pass
        s_norm = 0.0
        sc = _score_item(it, ctx, tau_days, s_norm)
        sc += _deterministic_jitter(ctx["video_id"], vid, user_uid)
        scored.append((sc, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    sorted_items = [it for _, it in scored]
    final_items = _apply_diversity(
        sorted_items,
        limit=limit,
        max_same_author_top10=q_same_author,
        max_same_cat_top10=q_same_cat,
    )

    # Build output
    out: List[Dict[str, Any]] = []
    for it in final_items:
        vid = it["video_id"]
        r = by_id.get(vid, {})
        thumb_url = build_storage_url(r["thumb_asset_path"]) if r.get("thumb_asset_path") else None
        thumb_anim_url = build_storage_url(r["thumb_anim_asset_path"]) if r.get("thumb_anim_asset_path") else None
        avatar_url = build_storage_url(r["avatar_asset_path"]) if r.get("avatar_asset_path") else None
        author_name = (r.get("username") or "").strip() or (it.get("username") or "").strip() or (it.get("channel_id") or "")
        uploaded_at = _uploaded_at_str(r.get("created_at") or it.get("created_at"))
        out.append(
            {
                "video_id": vid,
                "title": it.get("title") or "",
                "description": it.get("description") or "",
                "author": author_name or "",
                "category": it.get("category") or "",
                "views_count": int(it.get("views_count") or 0),
                "likes_count": int(it.get("likes_count") or 0),
                "uploaded_at": uploaded_at,
                "thumb_url": thumb_url,
                "thumb_url_anim": thumb_anim_url,
                "avatar_url": avatar_url,
            }
        )

    # Hard fill up to limit from trending as a last resort (no scoring), excluding current and duplicates
    if len(out) < limit:
        try:
            extra = await fetch_trending(limit=limit * 2, days=tau_days)
        except Exception:
            extra = []
        have = {x["video_id"] for x in out}
        for d in extra:
            vid = d.get("video_id")
            if not vid or vid in have or vid == video_id:
                continue
            out.append(
                {
                    "video_id": vid,
                    "title": d.get("title") or "",
                    "description": d.get("description") or "",
                    "author": d.get("author") or "",
                    "category": d.get("category") or "",
                    "views_count": int(d.get("views_count") or 0),
                    "likes_count": int(d.get("likes_count") or 0),
                    "uploaded_at": d.get("uploaded_at"),
                    "thumb_url": d.get("thumb_url"),
                    "thumb_url_anim": d.get("thumb_url_anim"),
                    "avatar_url": d.get("avatar_url"),
                }
            )
            have.add(vid)
            if len(out) >= limit:
                break

    return out