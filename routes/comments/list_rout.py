from fastapi import APIRouter, Query
from typing import Dict, Any
from services.comments.comment_tree_srv import fetch_root, build_tree_payload, fetch_texts_for_comments
from config.comments_config import comments_settings

router = APIRouter(prefix="/comments", tags=["comments"])


@router.get("/list")
async def list_comments(video_id: str, include_hidden: bool = Query(False)) -> Dict[str, Any]:
    if not comments_settings.COMMENTS_ENABLED:
        return {"ok": True, "comments": [], "roots": []}

    root = await fetch_root(video_id)
    if not root:
        return {"ok": True, "comments": [], "roots": []}

    payload = build_tree_payload(root, show_hidden=include_hidden)
    texts = await fetch_texts_for_comments(video_id, root, show_hidden=include_hidden)

    return {
        "ok": True,
        "roots": payload["roots"],
        "children_map": payload["children_map"],
        "comments": payload["comments"],
        "texts": texts
    }