from typing import Any, Optional, Dict
import json

async def set_video_captions(conn, video_id: str, rel_vtt: str, lang: str, meta: Dict[str, Any]) -> None:
    await conn.execute(
        """
        UPDATE videos
        SET captions_vtt = $2,
            captions_lang = $3,
            captions_meta = $4,
            captions_ready = TRUE
        WHERE video_id = $1
        """,
        video_id,
        rel_vtt,
        lang,
        json.dumps(meta),
    )

async def reset_video_captions(conn, video_id: str) -> None:
    await conn.execute(
        """
        UPDATE videos
        SET captions_vtt = NULL,
            captions_lang = NULL,
            captions_meta = NULL,
            captions_ready = FALSE
        WHERE video_id = $1
        """,
        video_id,
    )

async def get_video_captions_status(conn, video_id: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT captions_vtt, captions_ready, captions_lang, captions_meta FROM videos WHERE video_id=$1",
        video_id,
    )
    if not row:
        return None
    return {
        "captions_vtt": row["captions_vtt"],
        "captions_ready": bool(row["captions_ready"]),
        "captions_lang": row["captions_lang"],
        "captions_meta": row["captions_meta"],
    }