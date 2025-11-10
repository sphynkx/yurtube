from typing import Dict, Any
from db.comments.mongo_conn import root_coll


async def like_delta(video_id: str, comment_id: str, delta_like: int = 0, delta_dislike: int = 0) -> Dict[str, Any]:
    inc = {}
    totals_inc = {}
    if delta_like:
        inc[f"comments.{comment_id}.likes"] = delta_like
        totals_inc["totals.likes_sum"] = delta_like
    if delta_dislike:
        inc[f"comments.{comment_id}.dislikes"] = delta_dislike
        totals_inc["totals.dislikes_sum"] = delta_dislike

    if not inc:
        return {"error": "no_delta"}

    await root_coll().update_one(
        {"video_id": video_id},
        {"$inc": {**inc, **totals_inc}}
    )
    return {"ok": True}