from typing import Any, Dict, List, Optional


async def get_owned_video_full(conn, video_id: str, owner_uid: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full video row for edit pages, restricted to owner.
    """
    row = await conn.fetchrow(
        """
        SELECT v.*,
               u.username, u.channel_id,
               ua.path AS avatar_asset_path,
               a.path AS thumb_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        WHERE v.video_id = $1 AND v.author_uid = $2
        """,
        video_id,
        owner_uid,
    )
    return dict(row) if row else None


async def update_video_meta(
    conn,
    video_id: str,
    *,
    title: str,
    description: str,
    status: str,
    category_id: Optional[str],
    is_age_restricted: bool,
    is_made_for_kids: bool,
    allow_comments: bool,
    license_str: str,
) -> None:
    """
    Update meta fields of a video.
    """
    await conn.execute(
        """
        UPDATE videos
        SET title = $2,
            description = $3,
            status = $4,
            category_id = $5,
            is_age_restricted = $6,
            is_made_for_kids = $7,
            allow_comments = $8,
            license = $9
        WHERE video_id = $1
        """,
        video_id,
        title,
        description,
        status,
        (category_id or None),
        is_age_restricted,
        is_made_for_kids,
        allow_comments,
        (license_str or "standard").strip(),
    )


async def update_thumb_pref_offset(conn, video_id: str, offset_sec: int) -> None:
    """
    Store preferred thumbnail offset.
    """
    await conn.execute(
        "UPDATE videos SET thumb_pref_offset = $2 WHERE video_id = $1",
        video_id,
        max(0, int(offset_sec)),
    )


async def set_video_embed_params(conn, video_id: str, allow_embed: bool, params_json: str) -> None:
    """
    Update allow_embed and embed_params for a video.
    """
    await conn.execute(
        """
        UPDATE videos
        SET allow_embed = $2,
            embed_params = $3::jsonb
        WHERE video_id = $1
        """,
        video_id,
        allow_embed,
        params_json,
    )


async def fetch_watch_video_full(conn, video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch watch page data for a video.
    """
    row = await conn.fetchrow(
        """
        SELECT
          v.video_id,
          v.title,
          v.description,
          v.storage_path,
          v.created_at,
          v.views_count,
          v.likes_count,
          v.allow_embed,
          v.embed_params,
          u.username,
          u.channel_id,
          vcat.name AS category,
          vthumb.path AS thumb_asset_path,
          vanim.path  AS thumb_anim_asset_path,
          uava.path   AS avatar_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN categories vcat ON vcat.category_id = v.category_id
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
        WHERE v.video_id = $1
        """,
        video_id,
    )
    return dict(row) if row else None


async def fetch_embed_video_info(conn, video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch minimal embed data for a video.
    """
    row = await conn.fetchrow(
        """
        SELECT v.video_id, v.title, v.storage_path,
               a.path AS thumb_asset_path
        FROM videos v
        LEFT JOIN video_assets a
          ON a.video_id = v.video_id AND a.asset_type = 'thumbnail_default'
        WHERE v.video_id = $1
        """,
        video_id,
    )
    return dict(row) if row else None