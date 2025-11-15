from typing import Optional, Tuple, Dict, Any
import asyncpg
import uuid

ReactionInt = int  # -1 (dislike), 0 (none), 1 (like)

def _to_type(v: ReactionInt) -> Optional[str]:
    if v == 1:
        return "like"
    if v == -1:
        return "dislike"
    return None

def _to_int(t: Optional[str]) -> ReactionInt:
    if t == "like":
        return 1
    if t == "dislike":
        return -1
    return 0

async def get_video_reaction_state(
    conn: asyncpg.Connection,
    user_uid: Optional[str],
    video_id: str,
) -> Dict[str, Any]:
    likes_row = await conn.fetchrow("SELECT likes_count FROM videos WHERE video_id = $1", video_id)
    likes_count = int(likes_row["likes_count"]) if likes_row else 0
    drow = await conn.fetchrow(
        "SELECT COUNT(*) AS c FROM reactions WHERE video_id = $1 AND reaction_type = 'dislike'",
        video_id,
    )
    dislikes_count = int(drow["c"] if drow and drow["c"] is not None else 0)

    my_reaction: ReactionInt = 0
    if user_uid:
        r = await conn.fetchrow(
            "SELECT reaction_type FROM reactions WHERE user_uid = $1 AND video_id = $2",
            user_uid,
            video_id,
        )
        my_reaction = _to_int(r["reaction_type"]) if r and r["reaction_type"] else 0

    return {
        "likes": likes_count,
        "dislikes": dislikes_count,
        "my_reaction": my_reaction,
    }

async def set_video_reaction(
    conn: asyncpg.Connection,
    user_uid: str,
    video_id: str,
    reaction: ReactionInt,  # -1, 0, 1
) -> Tuple[int, int, ReactionInt]:
    if reaction not in (-1, 0, 1):
        raise ValueError("invalid reaction")

    prev = await conn.fetchrow(
        "SELECT reaction_type FROM reactions WHERE user_uid = $1 AND video_id = $2",
        user_uid,
        video_id,
    )
    prev_type: Optional[str] = prev["reaction_type"] if prev and prev["reaction_type"] else None
    new_type: Optional[str] = _to_type(reaction)

    delta_like = 0
    if prev_type == "like" and new_type != "like":
        delta_like = -1
    elif prev_type != "like" and new_type == "like":
        delta_like = 1

    tr = conn.transaction()
    await tr.start()
    try:
        if new_type is None:
            # remove reaction if existed
            await conn.execute(
                "DELETE FROM reactions WHERE user_uid = $1 AND video_id = $2",
                user_uid,
                video_id,
            )
        elif prev_type is None:
            # insert new
            await conn.execute(
                """
                INSERT INTO reactions (reaction_uid, user_uid, video_id, reaction_type)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_uid, video_id) DO UPDATE SET reaction_type = EXCLUDED.reaction_type
                """,
                str(uuid.uuid4()),
                user_uid,
                video_id,
                new_type,
            )
        elif prev_type != new_type:
            # update type
            await conn.execute(
                "UPDATE reactions SET reaction_type = $3 WHERE user_uid = $1 AND video_id = $2",
                user_uid,
                video_id,
                new_type,
            )

        if delta_like != 0:
            await conn.execute(
                "UPDATE videos SET likes_count = GREATEST(0, likes_count + $2) WHERE video_id = $1",
                video_id,
                delta_like,
            )

        likes_row = await conn.fetchrow("SELECT likes_count FROM videos WHERE video_id = $1", video_id)
        likes_count = int(likes_row["likes_count"]) if likes_row else 0
        drow = await conn.fetchrow(
            "SELECT COUNT(*) AS c FROM reactions WHERE video_id = $1 AND reaction_type = 'dislike'",
            video_id,
        )
        dislikes_count = int(drow["c"] if drow and drow["c"] is not None else 0)
        await tr.commit()
    except Exception:
        await tr.rollback()
        raise

    return likes_count, dislikes_count, _to_int(new_type)