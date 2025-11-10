from typing import Dict, Any
from time import time
from db.comments.mongo_conn import root_coll, chunk_coll
from bson import ObjectId


try:
    from utils.comments.id_ut import short_uuid
except ImportError:
    short_uuid = None

async def create_comment(video_id: str, user: Dict[str, Any], text: str, parent_id: str | None = None) -> Dict[str, Any]:
    rc = root_coll()
    cc = chunk_coll()

    root = await rc.find_one({"video_id": video_id})
    if not root:
        root = {
            "video_id": video_id,
            "comments": {},
            "tree_aux": {"children_map": {}, "depth_index": {"0": []}}
        }
        ins = await rc.insert_one(root)
        root["_id"] = ins.inserted_id

    chunk_doc = {"video_id": video_id, "texts": {}}
    ins_chunk = await cc.insert_one(chunk_doc)
    chunk_id = ins_chunk.inserted_id

    if short_uuid:
        local_id = short_uuid(prefix="b")
    else:
        local_id = "b" + str(ObjectId())[:8]

    await cc.update_one({"_id": chunk_id}, {"$set": {f"texts.{local_id}": text}})

    cid = str(ObjectId())
    ts = int(time())
    comments = root["comments"]
    comments[cid] = {
        "author_uid": user["user_uid"],
        "author_name": user.get("username") or user.get("login") or user["user_uid"],
        "created_at": ts,
        "edited": False,
        "visible": True,
        "likes": 0,
        "dislikes": 0,
        "votes": {},
        "chunk_ref": {"chunk_id": str(chunk_id), "local_id": local_id},
        "parent_id": parent_id
    }

    tree = root["tree_aux"]
    children_map = tree.get("children_map", {})
    depth_index = tree.get("depth_index", {})

    if parent_id:
        children_map.setdefault(parent_id, []).append(cid)
    else:
        depth_index.setdefault("0", []).append(cid)

    await rc.update_one(
        {"_id": root["_id"]},
        {"$set": {"comments": comments, "tree_aux": {"children_map": children_map, "depth_index": depth_index}}}
    )

    return {"comment_id": cid}