from typing import Optional, Dict, Any
from bson import ObjectId
from config.comments_config import comments_settings
from db.comments.root_db import ensure_root, update_root
from db.comments.mongo_conn import root_coll
from db.comments.chunks_db import create_chunk, append_text
from services.comments.comment_sanitize_srv import sanitize_comment
from utils.comments.id_ut import short_uuid
from utils.comments.time_ut import now_unix
from utils.comments.size_ut import estimate_root_comment_entry_size


async def create_comment(
    video_id: str,
    author_uid: str,
    author_name: str,
    parent_id: Optional[str],
    raw_text: str,
    reply_to_user_uid: Optional[str],
    is_owner_moderator: bool = False
) -> Dict[str, Any]:
    root = await ensure_root(video_id)

    # Check ban state (full = permit to comment; soft = only hide)
    if any(b.get("user_uid") == author_uid for b in root.get("bans", {}).get("full", [])):
        return {"error": "user_fully_banned"}
    if any(b.get("user_uid") == author_uid for b in root.get("bans", {}).get("soft", [])):
        # MVP: permit to publish ( or change to visible=False)
        return {"error": "user_soft_banned"}

    safe_text, errors = sanitize_comment(raw_text)
    if errors:
        return {"error": "sanitize_failed", "details": errors}

    max_depth = root.get("settings_snapshot", {}).get("max_depth", comments_settings.COMMENTS_MAX_DEPTH)

    # tree depth
    depth = 0
    if parent_id:
        parent = root.get("comments", {}).get(parent_id)
        if not parent:
            return {"error": "parent_not_found"}
        depth = (parent.get("depth") or 0) + 1
        if depth > max_depth:
            # Cut to parent
            gp = parent.get("parent_id")
            if gp and root["comments"].get(gp):
                parent_id = gp
                depth = (root["comments"][gp].get("depth") or 0) + 1
            else:
                parent_id = None
                depth = 0

    # Choose chunk (last valid or create new)
    chunks = root.get("chunks", [])
    use_chunk_id: ObjectId
    if not chunks:
        use_chunk_id = await create_chunk(video_id)
    else:
        last = chunks[-1]
        if (last.get("approx_size") or 0) >= comments_settings.COMMENTS_SOFT_CHUNK_LIMIT_BYTES:
            use_chunk_id = await create_chunk(video_id)
        else:
            use_chunk_id = last["chunk_id"]

    comment_id = short_uuid(prefix="c")
    local_id = short_uuid(prefix="b")

    # Write comment text
    await append_text(video_id, ObjectId(use_chunk_id), local_id, safe_text)

    visible = True
    created_ts = now_unix()

    # Build tech-record
    new_entry = {
        "author_uid": author_uid,
        "author_name": author_name,
        "parent_id": parent_id,
        "reply_to_user_uid": reply_to_user_uid,
        "depth": depth,
        "visible": visible,
        "hidden_reason": None,
        "likes": 0,
        "dislikes": 0,
        "reactions": {},
        "created_at": created_ts,
        "edited_at": None,
        "edited": False,
        "format_flags": {},
        "chunk_ref": {"chunk_id": str(use_chunk_id), "local_id": local_id}
    }

    # Assessment of additional size of root (approx.)
    add_sz = estimate_root_comment_entry_size(comment_id, new_entry)

    # Refresh root: comments, totals, seq, approx_size
    set_patch = {
        f"comments.{comment_id}": new_entry,
        "updated_at": created_ts,
    }
    inc_patch = {
        "totals.comments_count_total": 1,
        "totals.comments_count_visible": 1,
        "comment_seq": 1,
        "approx_size": add_sz
    }
    await update_root(video_id, set_patch, inc_patch)

    # Refresh tree
    tree_updates = {}
    # children_map
    if parent_id:
        # Add child to array (MVP)
        parent_children = root.get("tree_aux", {}).get("children_map", {}).get(parent_id, [])
        parent_children = parent_children + [comment_id]
        tree_updates[f"tree_aux.children_map.{parent_id}"] = parent_children
    else:
        tree_updates[f"tree_aux.children_map.{comment_id}"] = []

    # depth_index
    dkey = str(depth)
    dlist = root.get("tree_aux", {}).get("depth_index", {}).get(dkey, [])
    dlist = dlist + [comment_id]
    tree_updates[f"tree_aux.depth_index.{dkey}"] = dlist

    await update_root(video_id, tree_updates)

    return {"ok": True, "comment_id": comment_id, "created_at": created_ts}