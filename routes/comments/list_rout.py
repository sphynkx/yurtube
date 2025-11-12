from fastapi import APIRouter, Query, Depends
from typing import Dict, Any, Optional
from services.comments.comment_tree_srv import fetch_root, build_tree_payload, fetch_texts_for_comments
from config.comments_config import comments_settings
from utils.security_ut import get_current_user

router = APIRouter(prefix="/comments", tags=["comments"])

@router.get("/list")
async def list_comments(
    video_id: str,
    include_hidden: bool = Query(False),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
) -> Dict[str, Any]:
    if not comments_settings.COMMENTS_ENABLED:
        return {"ok": True, "comments": [], "roots": []}

    root = await fetch_root(video_id)
    if not root:
        return {"ok": True, "comments": [], "roots": []}

    uid = None
    if current_user and "user_uid" in current_user:
        uid = current_user["user_uid"]

    payload = build_tree_payload(root, current_uid=uid, show_hidden=include_hidden)
    texts = await fetch_texts_for_comments(video_id, root, show_hidden=include_hidden)

    # Get video author to mark author's likes on comments
    video_author_uid: Optional[str] = None
    try:
        from db import get_conn, release_conn
        from db.videos_db import get_video
        conn = await get_conn()
        try:
            v = await get_video(conn, video_id)
            if v and "author_uid" in v:
                video_author_uid = v["author_uid"]
        finally:
            await release_conn(conn)
    except Exception:
        video_author_uid = None

    # Collect unique author UIDs for avatars
    author_uids = set()
    for cid, meta in payload["comments"].items():
        # mark liked_by_author
        if video_author_uid:
            votes = (meta.get("votes") or {})
            try:
                meta["liked_by_author"] = int(votes.get(video_author_uid, 0)) == 1
            except Exception:
                meta["liked_by_author"] = False
            payload["comments"][cid] = meta

        uid_meta = meta.get("author_uid")
        if uid_meta:
            author_uids.add(uid_meta)

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
                    author_avatars[au] = build_storage_url(p)
                else:
                    author_avatars[au] = "/static/img/avatar_default.svg"
        finally:
            await release_conn(conn)

    return {
        "ok": True,
        "roots": payload["roots"],
        "children_map": payload["children_map"],
        "comments": payload["comments"],
        "texts": texts,
        "avatars": author_avatars
    }