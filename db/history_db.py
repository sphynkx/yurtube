from typing import Optional

async def clear_history(conn, user_uid: str) -> None:
    await conn.execute("DELETE FROM views WHERE user_uid = $1", user_uid)

async def remove_history_item(conn, user_uid: str, video_id: str) -> None:
    await conn.execute(
        "DELETE FROM views WHERE user_uid = $1 AND video_id = $2",
        user_uid,
        video_id,
    )