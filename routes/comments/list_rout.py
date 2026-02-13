from fastapi import APIRouter, Query, Depends
from typing import Dict, Any, Optional, List, Set

import logging
log = logging.getLogger("comments_list")

try:
    from services.ytcomments.ytcomments_adapter import fetch_root, build_tree_payload, fetch_texts_for_comments
    log.info("comments_list: using ytcomments_adapter")
    print("comments_list: using ytcomments_adapter")
except Exception as e:
    log.error("comments_list: ytcomments_adapter import failed: %s", e)
    raise

from config.comments_cfg import comments_settings
from utils.security_ut import get_current_user
import json

router = APIRouter(prefix="/comments", tags=["comments"])


@router.get("/list")
async def list_comments(
    video_id: str,
    include_hidden: bool = Query(False),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    log.info("comments_list: called video_id=%s include_hidden=%s", video_id, include_hidden)
    print(f"comments_list: called video_id={video_id} include_hidden={include_hidden}")

    if not comments_settings.COMMENTS_ENABLED:
        return _empty(False)

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
                ep = _parse_ep(v.get("embed_params"))
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

    uid = current_user.get("user_uid") if current_user and "user_uid" in current_user else None
    viewer_is_owner = bool(uid and video_author_uid and str(uid) == str(video_author_uid))

    root = await fetch_root(video_id, include_deleted=True)
    if not root:
        return _empty(True)

    payload = build_tree_payload(root, current_uid=uid, show_hidden=include_hidden)

    payload["children_map"] = _build_children_map(payload["comments"])
    payload["roots"] = _sort_ids_by_created(payload["roots"], payload["comments"])

    if soft_banned:
        payload = _filter_and_reparent_by_authors(payload, soft_banned)

    must_hide_deleted = (hide_deleted == "all") or (hide_deleted == "owner" and not viewer_is_owner)
    if must_hide_deleted:
        payload = _filter_and_reparent_tombstones(payload)

    # Tombstone marking: only when deleted comments are allowed to be visible
    # (hide_deleted == "none") OR ("owner" and viewer_is_owner)
    if not must_hide_deleted:
        for _, meta in (payload.get("comments") or {}).items():
            if not isinstance(meta, dict):
                continue
            is_del = bool(meta.get("is_deleted")) or (meta.get("visible") in (False, 0, "false", "False"))
            if is_del:
                meta["tombstone"] = True
                meta["visible"] = False

    texts = await fetch_texts_for_comments(video_id, payload, show_hidden=include_hidden)

    author_uids = set()
    for cid, meta in payload["comments"].items():
        meta["my_vote"] = 0
        meta["liked_by_author"] = False
        payload["comments"][cid] = meta
        au = meta.get("author_uid")
        if au:
            author_uids.add(au)

    votes_map: Dict[str, int] = {}
    if uid:
        try:
            from services.ytcomments.client_srv import get_ytcomments_client, UserContext

            client = get_ytcomments_client()
            ctx = UserContext(
                user_uid=str(uid),
                username=str(current_user.get("username") or "") if current_user else None,
                channel_id=str(current_user.get("channel_id") or "") if current_user else None,
            )
            comment_ids = list(payload.get("comments", {}).keys())
            vm = await client.get_my_votes(video_id=video_id, comment_ids=comment_ids, ctx=ctx)
            votes_map = dict(vm or {})
        except Exception as e:
            log.warning("comments_list: get_my_votes failed: %s", e)
            votes_map = {}

    for cid, meta in payload["comments"].items():
        v = 0
        try:
            v = int(votes_map.get(cid, 0) or 0)
        except Exception:
            v = 0
        if v not in (-1, 0, 1):
            v = 0
        meta["my_vote"] = v
        meta["liked_by_author"] = bool(viewer_is_owner and v == 1)

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
                    if p.endswith("avatar.png"):
                        small_rel = p[: -len("avatar.png")] + "avatar_small.png"
                        author_avatars[au] = build_storage_url(small_rel)
                    else:
                        author_avatars[au] = build_storage_url(p)
                else:
                    author_avatars[au] = "/static/img/avatar_default.svg"
        finally:
            await release_conn(conn)

    payload["roots"] = _sort_ids_by_created(payload["roots"], payload["comments"])
    payload["children_map"] = _build_children_map(payload["comments"])

    return {
        "ok": True,
        "comments_enabled": True,
        "moderator": bool(viewer_is_owner),
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
        return {
            **payload,
            "children_map": _build_children_map(comments),
            "roots": _sort_ids_by_created([cid for cid, m in comments.items() if m.get("parent_id") is None], comments),
        }

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
        return {
            **payload,
            "children_map": _build_children_map(comments),
            "roots": _sort_ids_by_created([cid for cid, m in comments.items() if m.get("parent_id") is None], comments),
        }

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