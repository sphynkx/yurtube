from datetime import datetime
from typing import Any, Dict, Optional, Tuple, List, Set
from bson import ObjectId
from .mongo_conn import root_coll, chunk_coll
from config.comments_cfg import comments_settings
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


async def delete_all_comments_for_video(video_id: str) -> Dict[str, int]:
    """
    Delete the root document and all chunk documents referenced by it.
    Returns dict with counts:
      { "root_deleted": 0|1, "chunks_deleted": <int> }
    """
    doc = await root_coll().find_one({"video_id": video_id})
    if not doc:
        return {"root_deleted": 0, "chunks_deleted": 0}

    # Collect chunk ids from comment metas
    obj_ids: List[ObjectId] = []
    str_ids: List[str] = []
    seen: Set[str] = set()

    comments: Dict[str, Any] = doc.get("comments") or {}
    for cid, meta in comments.items():
        if not isinstance(meta, dict):
            continue
        cref = meta.get("chunk_ref") or {}
        ch = cref.get("chunk_id")
        if not ch:
            continue
        key = str(ch)
        if key in seen:
            continue
        seen.add(key)
        # Try ObjectId first; fall back to string id
        try:
            obj_ids.append(ObjectId(key))
        except Exception:
            str_ids.append(key)

    # Delete root
    dr = await root_coll().delete_one({"video_id": video_id})
    root_deleted = int(dr.deleted_count or 0)

    # Delete chunks (by ObjectId and by string ids)
    chunks_deleted = 0
    if obj_ids:
        dm1 = await chunk_coll().delete_many({"_id": {"$in": obj_ids}})
        chunks_deleted += int(dm1.deleted_count or 0)
    if str_ids:
        dm2 = await chunk_coll().delete_many({"_id": {"$in": str_ids}})
        chunks_deleted += int(dm2.deleted_count or 0)

    return {"root_deleted": root_deleted, "chunks_deleted": chunks_deleted}