from typing import Dict, Any
##deprecated
##from db.comments.mongo_conn import root_coll


async def hide_comment(video_id: str, comment_id: str) -> Dict[str, Any]:
    # Switch visible=false, hidden_reason=user_removed (MVP)
    # TODO: implement recompute totals via likes of this comment
    await root_coll().update_one(
        {"video_id": video_id},
        {"$set": {f"comments.{comment_id}.visible": False,
                  f"comments.{comment_id}.hidden_reason": "user_removed"}}
    )
    return {"ok": True}


async def restore_comment(video_id: str, comment_id: str) -> Dict[str, Any]:
    await root_coll().update_one(
        {"video_id": video_id},
        {"$set": {f"comments.{comment_id}.visible": True,
                  f"comments.{comment_id}.hidden_reason": None}}
    )
    return {"ok": True}