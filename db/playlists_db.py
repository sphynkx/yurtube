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


async def ensure_favorites(conn: asyncpg.Connection, owner_uid: str) -> str:
    return await ensure_system_playlist(conn, owner_uid, FAVORITES_TYPE, "Favorites")


async def create_user_playlist(
    conn: asyncpg.Connection,
    owner_uid: str,
    name: str,
    visibility: str = "private",
) -> str:
    """
    Create a user playlist (type='user') and return playlist_id.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("playlist_name_required")
    if visibility not in ("private", "unlisted", "public"):
        visibility = "private"

    playlist_id = gen_id(12)
    await conn.execute(
        """
        INSERT INTO playlists (
            playlist_id, owner_uid, name, description, visibility,
            type, parent_id, cover_asset_path, is_loop, ordering_mode, share_token
        )
        VALUES ($1, $2, $3, NULL, $4, 'user', NULL, NULL, FALSE, 'manual', NULL)
        """,
        playlist_id,
        owner_uid,
        name,
        visibility,
    )
    return playlist_id


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


async def add_video_to_favorites(
    conn: asyncpg.Connection,
    owner_uid: str,
    video_id: str,
) -> bool:
    plid = await ensure_favorites(conn, owner_uid)
    return await add_video_to_playlist(conn, plid, video_id)


async def list_user_playlists_min(
    conn: asyncpg.Connection,
    owner_uid: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT playlist_id,
               name,
               type,
               visibility,
               items_count,
               cover_asset_path
        FROM playlists
        WHERE owner_uid = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        owner_uid,
        limit,
    )
    return [dict(r) for r in rows]


# -------- Owner/playlist helpers --------

async def get_owned_playlist(
    conn: asyncpg.Connection,
    playlist_id: str,
    owner_uid: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT playlist_id, owner_uid, name, description, visibility, type,
               cover_asset_path, items_count, created_at, updated_at
        FROM playlists
        WHERE playlist_id = $1 AND owner_uid = $2
        """,
        playlist_id,
        owner_uid,
    )
    return dict(row) if row else None


async def get_playlist_owner_uid(conn: asyncpg.Connection, playlist_id: str) -> Optional[str]:
    row = await conn.fetchrow(
        "SELECT owner_uid FROM playlists WHERE playlist_id = $1",
        playlist_id,
    )
    return row["owner_uid"] if row else None


async def update_playlist_name(
    conn: asyncpg.Connection,
    playlist_id: str,
    owner_uid: str,
    name: str,
) -> None:
    await conn.execute(
        """
        UPDATE playlists
        SET name = $3, updated_at = NOW()
        WHERE playlist_id = $1 AND owner_uid = $2
        """,
        playlist_id,
        owner_uid,
        name,
    )


async def get_playlist_cover_path(
    conn: asyncpg.Connection,
    playlist_id: str,
    owner_uid: str,
) -> Optional[str]:
    row = await conn.fetchrow(
        """
        SELECT cover_asset_path
        FROM playlists
        WHERE playlist_id = $1 AND owner_uid = $2
        """,
        playlist_id,
        owner_uid,
    )
    return (row["cover_asset_path"] if row and row["cover_asset_path"] else None)


async def set_playlist_cover_path(
    conn: asyncpg.Connection,
    playlist_id: str,
    owner_uid: str,
    rel_path: Optional[str],
) -> None:
    await conn.execute(
        """
        UPDATE playlists
        SET cover_asset_path = $3, updated_at = NOW()
        WHERE playlist_id = $1 AND owner_uid = $2
        """,
        playlist_id,
        owner_uid,
        rel_path,
    )


async def delete_playlist_by_owner(
    conn: asyncpg.Connection,
    playlist_id: str,
    owner_uid: str,
) -> None:
    await conn.execute(
        "DELETE FROM playlists WHERE playlist_id = $1 AND owner_uid = $2",
        playlist_id,
        owner_uid,
    )


async def remove_video_from_playlist(
    conn: asyncpg.Connection,
    playlist_id: str,
    video_id: str,
) -> None:
    await conn.execute(
        "DELETE FROM playlist_items WHERE playlist_id = $1 AND video_id = $2",
        playlist_id,
        video_id,
    )


async def reorder_playlist_items(
    conn: asyncpg.Connection,
    playlist_id: str,
    order: List[str],
) -> None:
    pos = 0
    for vid in order:
        await conn.execute(
            "UPDATE playlist_items SET position = $3 WHERE playlist_id = $1 AND video_id = $2",
            playlist_id,
            (vid or "").strip(),
            pos,
        )
        pos += 1


async def list_playlist_items_with_assets(
    conn: asyncpg.Connection,
    playlist_id: str,
) -> List[Dict[str, Any]]:
    """
    Return playlist items with joined video metadata and assets (as used in editor UI).
    """
    rows = await conn.fetch(
        """
        SELECT pi.playlist_id, pi.video_id, pi.position, pi.added_at,
               v.title,
               v.created_at AS video_created_at,
               v.thumb_pref_offset AS thumb_pref_offset,
               v.views_count AS views_count,
               v.likes_count AS likes_count,
               u.username,
               u.channel_id,
               vthumb.path AS thumb_asset_path,
               vanim.path  AS thumb_anim_asset_path,
               uava.path   AS avatar_asset_path
        FROM playlist_items AS pi
        JOIN videos AS v ON v.video_id = pi.video_id
        JOIN users  AS u ON u.user_uid = v.author_uid
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_default'
          LIMIT 1
        ) vthumb ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM video_assets
          WHERE video_id = v.video_id AND asset_type = 'thumbnail_anim'
          LIMIT 1
        ) vanim ON true
        LEFT JOIN LATERAL (
          SELECT path
          FROM user_assets
          WHERE user_uid = v.author_uid AND asset_type = 'avatar'
          LIMIT 1
        ) uava ON true
        WHERE pi.playlist_id = $1
        ORDER BY pi.position ASC, pi.added_at ASC
        """,
        playlist_id,
    )
    return [dict(r) for r in rows]


async def update_playlist_visibility(
    conn: asyncpg.Connection,
    playlist_id: str,
    owner_uid: str,
    visibility: str,
) -> None:
    """
    Update visibility for a playlist owned by owner_uid.
    """
    vis = (visibility or "").strip().lower()
    if vis not in ("private", "unlisted", "public"):
        raise ValueError("invalid_visibility")
    await conn.execute(
        """
        UPDATE playlists
        SET visibility = $3, updated_at = NOW()
        WHERE playlist_id = $1 AND owner_uid = $2
        """,
        playlist_id,
        owner_uid,
        vis,
    )


async def get_playlist_brief(
    conn: asyncpg.Connection,
    playlist_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Minimal info for showing playlist title in watch page.
    """
    row = await conn.fetchrow(
        """
        SELECT playlist_id, owner_uid, name, visibility, items_count
        FROM playlists
        WHERE playlist_id = $1
        """,
        playlist_id,
    )
    return dict(row) if row else None


async def list_user_playlists_flat_with_first(
    conn: asyncpg.Connection,
    owner_uid: str,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """
    Flat list of user's playlists with parent_id and first video id for quick linking.
    """
    rows = await conn.fetch(
        """
        SELECT
          p.playlist_id,
          p.name,
          p.type,
          p.parent_id,
          p.visibility,
          p.items_count,
          (
            SELECT pi.video_id
            FROM playlist_items pi
            WHERE pi.playlist_id = p.playlist_id
            ORDER BY pi.position ASC, pi.added_at ASC
            LIMIT 1
          ) AS first_video_id
        FROM playlists p
        WHERE p.owner_uid = $1
        ORDER BY p.name ASC
        LIMIT $2
        """,
        owner_uid,
        max(1, int(limit)),
    )
    return [dict(r) for r in rows]