## SRTG_DONE
## SRTG_2MODIFY: build_storage_url(
from fastapi import APIRouter, Query, Depends
from typing import Dict, Any, Optional, List, Set
from services.comments.comment_tree_srv import fetch_root, build_tree_payload, fetch_texts_for_comments
from config.comments_cfg import comments_settings
from utils.security_ut import get_current_user
import json

router = APIRouter(prefix="/comments", tags=["comments"])


@router.get("/list")
async def list_comments(
    video_id: str,
    include_hidden: bool = Query(False),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
) -> Dict[str, Any]:
    # Global toggle
    if not comments_settings.COMMENTS_ENABLED:
        return _empty(False)

    # Per-video flags
    video_allow = True
    video_author_uid: Optional[str] = None
    hide_deleted: str = "all"
    soft_banned: Set[str] = set()

    try:
        from db import get_conn, release_conn
        from db.videos_db import get_video
        conn = await get_conn()
        try:
            v = await get_video(conn, video_id)
            if v:
                video_allow = bool(v.get("allow_comments", True))
                video_author_uid = v.get("author_uid")
                ep = v.get("embed_params")
                ep = _parse_ep(ep)
                hv = str(ep.get("comments_hide_deleted", "") or "").strip()
                if hv in ("none", "owner", "all"):
                    hide_deleted = hv
                s_list = ep.get("comments_soft_ban_uids") or []
                if isinstance(s_list, list):
                    soft_banned = set([str(x).strip() for x in s_list if isinstance(x, str)])
        finally:
            await release_conn(conn)
    except Exception:
        pass

    if not video_allow:
        return _empty(False)

    root = await fetch_root(video_id)
    if not root:
        return _empty(True)

    uid = current_user.get("user_uid") if current_user and "user_uid" in current_user else None
    payload = build_tree_payload(root, current_uid=uid, show_hidden=include_hidden)
    texts = await fetch_texts_for_comments(video_id, root, show_hidden=include_hidden)

    # always rebuild children_map with sort by created_at (new in top)
    payload["children_map"] = _build_children_map(payload["comments"])
    payload["roots"] = _sort_ids_by_created(payload["roots"], payload["comments"])

    # Apply soft-ban with reparent
    if soft_banned:
        payload = _filter_and_reparent_by_authors(payload, soft_banned)

    # Apply hide_deleted with reparent
    if hide_deleted in ("none", "owner"):
        viewer_is_owner = (uid is not None and video_author_uid is not None and uid == video_author_uid)
        must_hide = (hide_deleted == "none") or (hide_deleted == "owner" and not viewer_is_owner)
        if must_hide:
            payload = _filter_and_reparent_tombstones(payload)

    # Mark liked_by_author and my_vote; collect avatars
    author_uids = set()
    for cid, meta in payload["comments"].items():
        # liked_by_author
        liked = False
        if video_author_uid:
            votes = (meta.get("votes") or {})
            v = votes.get(video_author_uid)
            try:
                liked = (int(v) == 1)
            except Exception:
                liked = (str(v) == "1")
        meta["liked_by_author"] = bool(liked)

        # my_vote (robust)
        if uid:
            votes = (meta.get("votes") or {})
            mv = 0
            if uid in votes:
                try:
                    mv = int(votes[uid])
                except Exception:
                    try:
                        mv = int(str(votes[uid]))
                    except Exception:
                        mv = 0
            meta["my_vote"] = mv

        payload["comments"][cid] = meta
        au = meta.get("author_uid")
        if au:
            author_uids.add(au)

    # Avatars map
    author_avatars: Dict[str, str] = {}
    if author_uids:
        from db import get_conn, release_conn
        from db.user_assets_db import get_user_avatar_path
        from utils.url_ut import build_storage_url
        conn = await get_conn()
        try:
            for au in author_uids:
                p = await get_user_avatar_path(conn, au)
                if p:
                    # Prefer small avatar if original path returned
                    if p.endswith("avatar.png"):
                        small_rel = p[: -len("avatar.png")] + "avatar_small.png"
                        author_avatars[au] = build_storage_url(small_rel)
                    else:
                        author_avatars[au] = build_storage_url(p)
                else:
                    author_avatars[au] = "/static/img/avatar_default.svg"
        finally:
            await release_conn(conn)

    is_moderator = bool(uid and video_author_uid and uid == video_author_uid)

    # for roots and children - new in top
    payload["roots"] = _sort_ids_by_created(payload["roots"], payload["comments"])
    payload["children_map"] = _build_children_map(payload["comments"])

    return {
        "ok": True,
        "comments_enabled": True,
        "moderator": is_moderator,             # curr user is author of video (moderator)
        "video_author_uid": video_author_uid,
        "roots": payload["roots"],
        "children_map": payload["children_map"],
        "comments": payload["comments"],
        "texts": texts,
        "avatars": author_avatars,
    }


def _empty(enabled: bool) -> Dict[str, Any]:
    return {
        "ok": True,
        "comments_enabled": enabled,
        "comments": {},
        "roots": [],
        "children_map": {},
        "texts": {},
        "avatars": {},
    }


def _parse_ep(raw) -> Dict[str, Any]:
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _sort_ids_by_created(ids: List[str], comments: Dict[str, Dict[str, Any]]) -> List[str]:
    return sorted(ids or [], key=lambda cid: int((comments.get(cid) or {}).get("created_at", 0)), reverse=True)


def _build_children_map(comments: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    # Group children and sort every group by created_at (new in top)
    mapping: Dict[str, List[str]] = {}
    for cid, meta in (comments or {}).items():
        pid = meta.get("parent_id")
        if pid is None:
            continue
        mapping.setdefault(pid, []).append(cid)
    for pid, arr in mapping.items():
        mapping[pid] = _sort_ids_by_created(arr, comments)
    return mapping


def _filter_and_reparent_tombstones(payload: Dict[str, Any]) -> Dict[str, Any]:
    comments: Dict[str, Dict[str, Any]] = dict(payload.get("comments") or {})
    children: Dict[Optional[str], List[str]] = {}
    for cid, meta in comments.items():
        pid = meta.get("parent_id")
        children.setdefault(pid, []).append(cid)

    def is_tomb(meta: Dict[str, Any]) -> bool:
        if bool(meta.get("tombstone")) is True:
            return True
        vis = meta.get("visible")
        if vis in (False, 0, "false", "False"):
            return True
        return False

    to_remove = set([cid for cid, m in comments.items() if is_tomb(m)])
    if not to_remove:
        return {**payload, "children_map": _build_children_map(comments),
                "roots": _sort_ids_by_created([cid for cid, m in comments.items() if m.get("parent_id") is None], comments)}

    for rid in to_remove:
        pid = comments.get(rid, {}).get("parent_id")
        if pid in children:
            children[pid] = [x for x in children[pid] if x != rid]

    def nearest_alive(parent_id: Optional[str]) -> Optional[str]:
        cur = parent_id
        while cur is not None:
            if cur not in to_remove:
                return cur
            cur = comments.get(cur, {}).get("parent_id")
        return None

    for rid in list(to_remove):
        for child in list(children.get(rid, []) or []):
            new_parent = nearest_alive(comments.get(rid, {}).get("parent_id"))
            comments[child]["parent_id"] = new_parent
            children.setdefault(new_parent, []).append(child)
        children[rid] = []

    for rid in to_remove:
        comments.pop(rid, None)

    new_roots = [cid for cid, m in comments.items() if m.get("parent_id") is None]
    return {
        **payload,
        "roots": _sort_ids_by_created(new_roots, comments),
        "comments": comments,
        "children_map": _build_children_map(comments),
    }


def _filter_and_reparent_by_authors(payload: Dict[str, Any], banned_authors: Set[str]) -> Dict[str, Any]:
    comments: Dict[str, Dict[str, Any]] = dict(payload.get("comments") or {})
    children: Dict[Optional[str], List[str]] = {}
    for cid, meta in comments.items():
        pid = meta.get("parent_id")
        children.setdefault(pid, []).append(cid)

    to_remove = set()
    for cid, meta in comments.items():
        au = str(meta.get("author_uid") or "").strip()
        if au in banned_authors:
            to_remove.add(cid)

    if not to_remove:
        return {**payload, "children_map": _build_children_map(comments),
                "roots": _sort_ids_by_created([cid for cid, m in comments.items() if m.get("parent_id") is None], comments)}

    for rid in to_remove:
        pid = comments.get(rid, {}).get("parent_id")
        if pid in children:
            children[pid] = [x for x in children[pid] if x != rid]

    def nearest_alive(parent_id: Optional[str]) -> Optional[str]:
        cur = parent_id
        while cur is not None:
            if cur not in to_remove:
                return cur
            cur = comments.get(cur, {}).get("parent_id")
        return None

    for rid in list(to_remove):
        for child in list(children.get(rid, []) or []):
            new_parent = nearest_alive(comments.get(rid, {}).get("parent_id"))
            comments[child]["parent_id"] = new_parent
            children.setdefault(new_parent, []).append(child)
        children[rid] = []
    for rid in to_remove:
        comments.pop(rid, None)

    new_roots = [cid for cid, m in comments.items() if m.get("parent_id") is None]
    return {
        **payload,
        "roots": _sort_ids_by_created(new_roots, comments),
        "comments": comments,
        "children_map": _build_children_map(comments),
    }