from typing import Any, Dict, List, Optional
import logging
import os
import collections

from services.ytcomments.client_srv import get_ytcomments_client, CommentDTO

log = logging.getLogger("ytcomments_adapter")


def _meta_from_dto(c: CommentDTO) -> Dict[str, Any]:
    author_name = (c.username or c.channel_id or "") or None
    if not author_name:
        uid = c.user_uid or ""
        author_name = uid[:12] + "…" if len(uid) > 12 else (uid or "user")

    return {
        "comment_id": c.id,
        "video_id": c.video_id,
        "author_uid": c.user_uid,
        "author_name": author_name,
        "username": c.username or "",
        "channel_id": c.channel_id or "",
        "parent_id": c.parent_id,
        "content_html": c.content_html or "",
        "content_raw": c.content_raw or "",
        "is_deleted": bool(c.is_deleted),
        "visible": not bool(c.is_deleted),
        "tombstone": False,
        "edited": bool(c.edited),
        "created_at": int(c.created_at_ms),
        "updated_at": int(c.updated_at_ms),
        "reply_count": int(c.reply_count),
        "likes": int(getattr(c, "likes", 0) or 0),
        "dislikes": int(getattr(c, "dislikes", 0) or 0),
        # will be filled in routes/comments/list_rout.py via GetMyVotes
        "my_vote": 0,
        "liked_by_author": False,
    }


def _sort_ids_by_created(ids: List[str], comments: Dict[str, Dict[str, Any]], newest_first: bool = True) -> List[str]:
    keyf = lambda cid: int(comments.get(cid, {}).get("created_at") or 0)
    return sorted(ids, key=keyf, reverse=newest_first)


async def _fetch_via_service(video_id: str, page_size_top: int, sort_top: str, include_deleted: bool) -> Dict[str, Any]:
    client = get_ytcomments_client()

    top_page = await client.list_top(
        video_id=video_id,
        page_size=page_size_top,
        page_token="",
        sort=("newest_first" if sort_top == "newest_first" else "oldest_first"),
        include_deleted=bool(include_deleted),
        ctx=None,
    )

    comments: Dict[str, Dict[str, Any]] = {}
    children_map: Dict[Optional[str], List[str]] = {}
    roots: List[str] = []

    for c in top_page.items:
        meta = _meta_from_dto(c)
        meta["parent_id"] = None
        comments[c.id] = meta
        roots.append(c.id)
        children_map.setdefault(None, []).append(c.id)

    try:
        max_depth = int(os.getenv("YTCOMMENTS_MAX_DEPTH", "8"))
    except Exception:
        max_depth = 8

    queue = collections.deque([(rid, 1) for rid in roots])
    visited = set()
    while queue:
        parent_id, depth = queue.popleft()
        if parent_id in visited:
            continue
        visited.add(parent_id)

        if depth > max_depth:
            continue

        rep_page = await client.list_replies(
            video_id=video_id,
            parent_id=parent_id,
            page_size=500,
            page_token="",
            sort="oldest_first",
            include_deleted=bool(include_deleted),
            ctx=None,
        )

        if not rep_page.items:
            continue

        for rc in rep_page.items:
            if rc.id not in comments:
                comments[rc.id] = _meta_from_dto(rc)
            comments[rc.id]["parent_id"] = parent_id
            children_map.setdefault(parent_id, []).append(rc.id)
            queue.append((rc.id, depth + 1))

    newest = (sort_top == "newest_first")
    for pid, arr in list(children_map.items()):
        children_map[pid] = _sort_ids_by_created(
            arr,
            comments,
            newest_first=(pid is None and newest) or (pid is not None and False),
        )

    counts = await client.get_counts(video_id, ctx=None)

    return {
        "video_id": video_id,
        "comments": comments,
        "roots": roots,
        "children_map": children_map,
        "totals": {
            "comments_count_total": int(counts.get("total_count", 0)),
            "comments_count_visible": int(counts.get("top_level_count", 0)),
        },
    }


async def fetch_root(
    video_id: str,
    page_size_top: int = 50,
    sort_top: str = "newest_first",
    include_deleted: bool = False,
) -> Any:
    """
    No legacy fallback: always use ytcomments service.
    """
    log.info("ytcomments_adapter: fetch_root(video_id=%s)", video_id)
    return await _fetch_via_service(video_id, page_size_top, sort_top, include_deleted)


def build_tree_payload(
    payload: Any,
    current_uid: Optional[str] = None,
    show_hidden: bool = False,
    hide_deleted: Optional[str] = None,
    banned_authors: Optional[List[str]] = None,
    limit_children: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Service payload is already in the expected structure.
    Legacy path removed.
    """
    if isinstance(payload, dict) and isinstance(payload.get("comments"), dict):
        comments: Dict[str, Dict[str, Any]] = dict(payload.get("comments") or {})
        children_map: Dict[Optional[str], List[str]] = dict(payload.get("children_map") or {})
        roots: List[str] = list(payload.get("roots") or [])

        for rid in roots:
            if rid in comments:
                comments[rid]["parent_id"] = None

        for cid, meta in comments.items():
            pid = meta.get("parent_id")
            children_map.setdefault(pid, [])
            if pid is None and cid not in roots:
                roots.append(cid)

        return {
            **payload,
            "comments": comments,
            "roots": roots,
            "children_map": children_map,
        }

    return {
        "video_id": payload.get("video_id") if isinstance(payload, dict) else "",
        "comments": {},
        "roots": [],
        "children_map": {},
        "totals": {"comments_count_total": 0, "comments_count_visible": 0},
    }


async def fetch_texts_for_comments(
    video_id: str,
    payload_or_ids: Any,
    show_hidden: bool = False,
    current_uid: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, str]:
    """
    For service payload we just reuse content_raw/content_html already present.
    Legacy path removed.
    """
    if isinstance(payload_or_ids, dict) and isinstance(payload_or_ids.get("comments"), dict):
        comments = payload_or_ids.get("comments") or {}
        out: Dict[str, str] = {}
        for cid, meta in comments.items():
            if not isinstance(meta, dict):
                continue
            if not meta.get("visible", True) and not show_hidden:
                continue
            html = meta.get("content_html") or meta.get("content_raw") or ""
            if html:
                out[cid] = html
                meta["cached_text"] = html
        return out

    return {}