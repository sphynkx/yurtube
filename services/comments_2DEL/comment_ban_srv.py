from typing import Dict, Any
from utils.comments.time_ut import now_unix
##deprecated
##from db.comments.mongo_conn import root_coll


async def soft_ban_user(video_id: str, user_uid: str, reason: str = "") -> Dict[str, Any]:
    ban_entry = {"user_uid": user_uid, "reason": reason, "banned_at": now_unix()}
    await root_coll().update_one(
        {"video_id": video_id},
        {"$addToSet": {"bans.soft": ban_entry}}
    )
    return {"ok": True}


async def unban_user(video_id: str, user_uid: str) -> Dict[str, Any]:
    await root_coll().update_one(
        {"video_id": video_id},
        {"$pull": {"bans.soft": {"user_uid": user_uid}}}
    )
    return {"ok": True}