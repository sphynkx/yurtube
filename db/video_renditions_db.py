from typing import Any, Dict, List


async def list_video_renditions(conn, video_id: str) -> List[Dict[str, Any]]:
    """
    Return renditions for a video.
    """
    rows = await conn.fetch(
        """
        SELECT preset, codec, status, storage_path, updated_at, error_message
        FROM video_renditions
        WHERE video_id = $1
        ORDER BY preset, codec
        """,
        video_id,
    )
    return [dict(r) for r in rows]


async def enqueue_video_renditions(conn, video_id: str, presets: List[str], codec: str) -> None:
    """
    Queue multiple renditions for processing.
    """
    c = (codec or "vp9").strip()
    for p in presets:
        await conn.execute(
            """
            INSERT INTO video_renditions (video_id, preset, codec, status)
            VALUES ($1, $2, $3, 'queued')
            ON CONFLICT (video_id, preset, codec)
            DO UPDATE SET status = 'queued', updated_at = now(), error_message = NULL
            """,
            video_id,
            p,
            c,
        )