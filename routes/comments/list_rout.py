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

    return {
        "ok": True,
        "roots": payload["roots"],
        "children_map": payload["children_map"],
        "comments": payload["comments"],
        "texts": texts
    }