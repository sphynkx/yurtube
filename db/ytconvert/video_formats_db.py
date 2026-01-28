from asyncpg import Connection
from typing import List


async def upsert_video_formats(conn: Connection, video_id: str, video_formats: List[str], audio_formats: List[str]) -> None:
    """
    Insert or update formats for a video.

    :param conn: Database connection object
    :param video_id: ID of the video
    :param video_formats: List of video formats (e.g., ['mp4', 'webm'])
    :param audio_formats: List of audio formats (e.g., ['mp3', 'ogg'])
    """
    # Upsert video formats
    for fmt in video_formats:
        await conn.execute(
            """
            INSERT INTO video_formats (video_id, format_type, format_name)
            VALUES ($1, 'video', $2)
            ON CONFLICT (video_id, format_name)
            DO UPDATE SET format_type = 'video'
            """,
            video_id,
            fmt,
        )

    # Upsert audio formats
    for fmt in audio_formats:
        await conn.execute(
            """
            INSERT INTO video_formats (video_id, format_type, format_name)
            VALUES ($1, 'audio', $2)
            ON CONFLICT (video_id, format_name)
            DO UPDATE SET format_type = 'audio'
            """,
            video_id,
            fmt,
        )