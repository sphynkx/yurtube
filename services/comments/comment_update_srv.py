from typing import Dict, Any, Optional
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
    cref = meta.get("chunk_ref") or {}
    chunk_id = cref.get("chunk_id")
    local_id = cref.get("local_id")
    if not (chunk_id and local_id):
        return {"error": "chunk_ref_invalid"}

    # Refresh text
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
    meta = comments.get(comment_id)
    if not meta:
        return {"error": "comment_not_found"}
    if meta.get("author_uid") != user_uid:
        return {"error": "forbidden"}
    if not meta.get("visible", True):
        return {"ok": True, "comment_id": comment_id}

    meta["visible"] = False
    meta["hidden_reason"] = "deleted_by_author"
    comments[comment_id] = meta
    await rc.update_one({"_id": root["_id"]}, {"$set": {"comments": comments}})
    return {"ok": True, "comment_id": comment_id}