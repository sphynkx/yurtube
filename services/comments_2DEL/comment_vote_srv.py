from typing import Dict, Any, Optional, Tuple
from bson import ObjectId
##deprecated
##from db.comments.mongo_conn import root_coll
from datetime import datetime

async def apply_vote(video_id: str, user_uid: str, comment_id: str, vote: int) -> Tuple[int, int, int]:
    col = root_coll()
    root = await col.find_one({"video_id": video_id})
    if not root:
        raise ValueError("root not found")

    comments: Dict[str, Any] = root.get("comments", {})
    meta = comments.get(comment_id)
    if not meta:
        raise ValueError("comment not found")

    votes: Dict[str, int] = meta.get("votes", {})
    prev = votes.get(user_uid, 0)

    if vote not in (-1, 0, 1):
        raise ValueError("invalid vote")

    if vote == prev:
        vote = 0

    if vote == 0:
        if user_uid in votes:
            del votes[user_uid]
    else:
        votes[user_uid] = vote

    meta["votes"] = votes

    likes = sum(1 for v in votes.values() if v == 1)
    dislikes = sum(1 for v in votes.values() if v == -1)
    meta["likes"] = likes
    meta["dislikes"] = dislikes

    comments[comment_id] = meta
    await col.update_one({"_id": root["_id"]}, {"$set": {"comments": comments}})
    return likes, dislikes, votes.get(user_uid, 0)