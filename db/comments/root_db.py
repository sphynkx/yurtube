from datetime import datetime
from typing import Any, Dict, Optional
from .mongo_conn import root_coll
from config.comments_config import comments_settings
from utils.comments.time_ut import now_unix


async def ensure_root(video_id: str) -> Dict[str, Any]:
    doc = await root_coll().find_one({"video_id": video_id})
    if doc:
        return doc
    init = {
        "video_id": video_id,
        "chunks": [],  # [{chunk_id, count, approx_size}]
        "comments": {},  # "cid": technical data (no comments texts!!)
        "tree_aux": {
            "children_map": {},   # "cid": [child_cids...]
            "depth_index": {}     # "depth": [cids...]
        },
        "totals": {
            "comments_count_total": 0,
            "comments_count_visible": 0,
            "likes_sum": 0,
            "dislikes_sum": 0
        },
        "bans": {
            "soft": [],  # [{user_uid, reason, banned_at(unix)}]
            "full": []
        },
        "settings_snapshot": {
            "max_depth": comments_settings.COMMENTS_MAX_DEPTH,
            "inline_children_limit": comments_settings.COMMENTS_MAX_CHILDREN_INLINE
        },
        "comment_seq": 0,  # Reserved: no need in case of short-uuid
        "chunk_seq": 0,
        "approx_size": 0,   # root size estimation
        "updated_at": now_unix(),
        "schema_version": 1
    }
    await root_coll().insert_one(init)
    return init


async def update_root(video_id: str, set_patch: Dict[str, Any], inc_patch: Optional[Dict[str, int]] = None):
    update: Dict[str, Any] = {"$set": {"updated_at": now_unix(), **set_patch}}
    if inc_patch:
        update["$inc"] = inc_patch
    await root_coll().update_one({"video_id": video_id}, update)