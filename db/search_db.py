from typing import Any, Dict, List


async def fetch_video_assets_by_ids(conn, video_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Bulk fetch assets and meta for given video ids.
    """
    rows = await conn.fetch(
        """
        SELECT
          v.video_id,
          v.created_at,
          v.author_uid,
          u.username,
          ua.path AS avatar_asset_path,
          vthumb.path AS thumb_asset_path,
          vanim.path AS thumb_anim_asset_path
        FROM videos v
        JOIN users u ON u.user_uid = v.author_uid
        LEFT JOIN user_assets ua
          ON ua.user_uid = v.author_uid AND ua.asset_type = 'avatar'
        LEFT JOIN video_assets vthumb
          ON vthumb.video_id = v.video_id AND vthumb.asset_type = 'thumbnail_default'
        LEFT JOIN video_assets vanim
          ON vanim.video_id = v.video_id AND vanim.asset_type = 'thumbnail_anim'
        WHERE v.video_id = ANY($1::text[])
        """,
        video_ids,
    )
    return [dict(r) for r in rows]