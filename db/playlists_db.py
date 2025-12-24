from typing import Optional, List, Dict, Any
import asyncpg

from utils.idgen_ut import gen_id


WATCH_LATER_TYPE = "system_watch_later"
FAVORITES_TYPE = "system_favorites"


async def ensure_system_playlist(
    conn: asyncpg.Connection,
    owner_uid: str,
    ptype: str,
    default_name: str,
) -> str:
    """
    Ensure that a system playlist of type ptype exists for owner.
    Returns playlist_id.
    """
    row = await conn.fetchrow(
        """
        SELECT playlist_id
        FROM playlists
        WHERE owner_uid = $1 AND type = $2
        LIMIT 1
        """,
        owner_uid,
        ptype,
    )
    if row:
        return row["playlist_id"]

    playlist_id = gen_id(12)
    await conn.execute(
        """
        INSERT INTO playlists (
            playlist_id, owner_uid, name, description, visibility,
            type, parent_id, cover_asset_path, is_loop, ordering_mode, share_token
        )
        VALUES ($1, $2, $3, NULL, 'private', $4, NULL, NULL, FALSE, 'manual', NULL)
        """,
        playlist_id,
        owner_uid,
        default_name,
        ptype,
    )
    return playlist_id


async def ensure_watch_later(conn: asyncpg.Connection, owner_uid: str) -> str:
    return await ensure_system_playlist(conn, owner_uid, WATCH_LATER_TYPE, "Watch later")


async def add_video_to_playlist(
    conn: asyncpg.Connection,
    playlist_id: str,
    video_id: str,
) -> bool:
    """
    Adds a video to playlist with next position. Returns True if inserted or already exists.
    """
    pos_row = await conn.fetchrow(
        "SELECT COALESCE(MAX(position), -1) AS maxpos FROM playlist_items WHERE playlist_id = $1",
        playlist_id,
    )
    next_pos = int(pos_row["maxpos"]) + 1 if pos_row and pos_row["maxpos"] is not None else 0

    await conn.execute(
        """
        INSERT INTO playlist_items (playlist_id, video_id, position)
        VALUES ($1, $2, $3)
        ON CONFLICT (playlist_id, video_id) DO NOTHING
        """,
        playlist_id,
        video_id,
        next_pos,
    )
    return True


async def add_video_to_watch_later(
    conn: asyncpg.Connection,
    owner_uid: str,
    video_id: str,
) -> bool:
    plid = await ensure_watch_later(conn, owner_uid)
    return await add_video_to_playlist(conn, plid, video_id)


async def list_user_playlists_min(
    conn: asyncpg.Connection,
    owner_uid: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT playlist_id, name, type, visibility, items_count
        FROM playlists
        WHERE owner_uid = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        owner_uid,
        limit,
    )
    return [dict(r) for r in rows]