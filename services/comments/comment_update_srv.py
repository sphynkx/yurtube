from typing import Dict, Any
from time import time
from bson import ObjectId
from db.comments.mongo_conn import root_coll, chunk_coll

async def update_comment_text(video_id: str, comment_id: str, user_uid: str, new_text: str) -> Dict[str, Any]:
    rc = root_coll()
    cc = chunk_coll()
    root = await rc.find_one({"video_id": video_id})
    if not root:
        return {"error": "root_not_found"}
    comments = root.get("comments", {})
    meta = comments.get(comment_id)
    if not meta:
        return {"error": "comment_not_found"}
    if meta.get("author_uid") != user_uid:
        return {"error": "forbidden"}
    if meta.get("tombstone"):
        return {"error": "cannot_edit_deleted"}

    cref = meta.get("chunk_ref") or {}
    chunk_id = cref.get("chunk_id")
    local_id = cref.get("local_id")
    if not (chunk_id and local_id):
        return {"error": "chunk_ref_invalid"}

    try:
        oid = ObjectId(chunk_id)
        filt = {"_id": oid}
    except Exception:
        filt = {"_id": chunk_id}

    await cc.update_one(filt, {"$set": {f"texts.{local_id}": new_text}})
    meta["edited"] = True
    meta["edited_at"] = int(time())
    comments[comment_id] = meta
    await rc.update_one({"_id": root["_id"]}, {"$set": {"comments": comments}})
    return {"ok": True, "comment_id": comment_id}


async def soft_delete_comment(video_id: str, comment_id: str, user_uid: str) -> Dict[str, Any]:
    rc = root_coll()
    root = await rc.find_one({"video_id": video_id})
    if not root:
        return {"error": "root_not_found"}

    comments = root.get("comments", {})
    tree_aux = root.get("tree_aux", {}) or {}
    children_map = tree_aux.get("children_map", {}) or {}
    depth_index = tree_aux.get("depth_index", {}) or {}

    meta = comments.get(comment_id)
    if not meta:
        return {"error": "comment_not_found"}
    if meta.get("author_uid") != user_uid:
        return {"error": "forbidden"}

    children = children_map.get(comment_id, [])
    has_children = bool(children)

    # Knot with children -> tombstone (leave in struct)
    if has_children:
        if meta.get("tombstone"):
            return {"ok": True, "comment_id": comment_id}
        meta["visible"] = False
        meta["tombstone"] = True
        meta["hidden_reason"] = "deleted_with_children"
        # Formally  set 0 for likes/dislikes
        meta["likes"] = 0
        meta["dislikes"] = 0
        meta["votes"] = {}
        comments[comment_id] = meta
    else:
        # leaf -> fully remove
        parent_id = meta.get("parent_id")
        if parent_id:
            lst = children_map.get(parent_id, [])
            children_map[parent_id] = [c for c in lst if c != comment_id]
        else:
            # This root: remove from depth_index["0"]
            rlst = depth_index.get("0", [])
            depth_index["0"] = [c for c in rlst if c != comment_id]
        # Remove comment also
        comments.pop(comment_id, None)
        # Clean comment children_map key
        children_map.pop(comment_id, None)

    tree_aux["children_map"] = children_map
    tree_aux["depth_index"] = depth_index

    await rc.update_one({"_id": root["_id"]},
                        {"$set": {"comments": comments, "tree_aux": tree_aux}})
    return {"ok": True, "comment_id": comment_id, "tombstone": has_children}