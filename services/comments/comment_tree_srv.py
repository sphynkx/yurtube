from typing import Dict, Any, List, Optional
from bson import ObjectId
from db.comments.mongo_conn import root_coll, chunk_coll
from config.comments_config import comments_settings

async def fetch_root(video_id: str) -> Optional[Dict[str, Any]]:
    return await root_coll().find_one({"video_id": video_id})

async def fetch_texts_for_comments(video_id: str, root_doc: Dict[str, Any], show_hidden: bool) -> Dict[str, str]:
    by_chunk: Dict[str, List[str]] = {}
    for cid, meta in root_doc.get("comments", {}).items():
        if not meta:
            continue
        if not show_hidden and not meta.get("visible", True):
            continue
        cref = meta.get("chunk_ref") or {}
        ch = cref.get("chunk_id")
        lid = cref.get("local_id")
        if ch and lid:
            by_chunk.setdefault(ch, []).append(lid)

    out: Dict[str, str] = {}
    for chunk_id_str, lids in by_chunk.items():
        try:
            oid = ObjectId(chunk_id_str)
            chunk = await chunk_coll().find_one({"_id": oid})
        except Exception:
            chunk = await chunk_coll().find_one({"_id": chunk_id_str})
        if not chunk:
            continue
        texts: Dict[str, str] = chunk.get("texts", {})
        for lid in lids:
            txt = texts.get(lid)
            if txt is not None:
                out[lid] = txt
    return out

def build_tree_payload(root_doc: Dict[str, Any], show_hidden: bool) -> Dict[str, Any]:
    comments = root_doc.get("comments", {})
    children_map = root_doc.get("tree_aux", {}).get("children_map", {})
    depth_idx = root_doc.get("tree_aux", {}).get("depth_index", {})
    roots = depth_idx.get("0", [])
    if not show_hidden:
        roots = [cid for cid in roots if comments.get(cid, {}).get("visible", True)]
    return {
        "roots": roots,
        "children_map": children_map,
        "comments": comments
    }