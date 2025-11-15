from typing import Dict, Any, List
from datetime import datetime
import asyncio
from redis.asyncio import Redis as RedisClient

from services.notifications.celery_app import celery_app
from config.notifications_config import notifications_config
from db import get_conn, release_conn
from db.notifications_db import insert_notification, get_user_prefs
from db.videos_db import get_video

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

def _run(coro):
    return _loop.run_until_complete(coro)

LIKE_PREFIX = "notif:likes:agg"

def _redis() -> RedisClient:
    return RedisClient.from_url(
        f"redis://{notifications_config.REDIS_HOST}:{notifications_config.REDIS_PORT}/{notifications_config.REDIS_DB}",
        encoding="utf-8",
        decode_responses=True,
    )

async def _redis_close(r: RedisClient):
    try:
        await r.aclose()
    except AttributeError:
        try:
            res = r.close()
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            pass

@celery_app.task(name="notifications.handle_event")
def handle_event(body: Dict[str, Any]):
    event = body.get("event")
    payload = body.get("payload") or {}
    if event == "comment.created":
        _run(_handle_comment_created(payload))
    elif event == "comment.reply":
        _run(_handle_comment_reply(payload))
    elif event == "comment.voted":
        _run(_handle_comment_voted(payload))
    elif event == "video.published":
        _run(_handle_video_published(payload))
    else:
        return

async def _load_prefs(conn, user_uid: str) -> Dict[str, Dict[str, Any]]:
    prefs = await get_user_prefs(conn, user_uid)
    if not prefs:
        return {
            k: {
                "inapp": notifications_config.DEFAULT_INAPP.get(k, True),
                "email": notifications_config.DEFAULT_EMAIL.get(k, False),
                "allow_unlisted": None,
            }
            for k in notifications_config.DEFAULT_INAPP.keys()
        }
    return prefs

async def _should_send(prefs: Dict[str, Dict[str, Any]], notif_type: str,
                       is_unlisted: bool = False, allow_unlisted: bool = True) -> bool:
    p = prefs.get(notif_type)
    if not p:
        return True
    if not p.get("inapp"):
        return False
    if notif_type == "video_published" and is_unlisted:
        if p.get("allow_unlisted") is not None:
            return bool(p.get("allow_unlisted"))
        return allow_unlisted
    return True

async def _handle_comment_created(payload: Dict[str, Any]):
    video_id = payload.get("video_id")
    actor_uid = payload.get("actor_uid")
    parent_comment_author_uid = payload.get("parent_comment_author_uid")
    comment_id = payload.get("comment_id")
    text_preview = (payload.get("text_preview") or "")[:notifications_config.MAX_PAYLOAD_PREVIEW_LEN]

    if not video_id or not actor_uid or not comment_id:
        return

    conn = await get_conn()
    try:
        v = await get_video(conn, video_id)
        if not v:
            return
        video_author = v.get("author_uid")
        video_title = v.get("title") or ""
        if video_author and video_author != actor_uid:
            prefs = await _load_prefs(conn, video_author)
            if await _should_send(prefs, "comment_created"):
                await insert_notification(
                    conn,
                    video_author,
                    "comment_created",
                    {
                        "video_id": video_id,
                        "video_title": video_title[:120],
                        "comment_id": comment_id,
                        "actor_uid": actor_uid,
                        "text_preview": text_preview,
                    },
                )
        if parent_comment_author_uid and parent_comment_author_uid not in (actor_uid, video_author):
            prefs2 = await _load_prefs(conn, parent_comment_author_uid)
            if await _should_send(prefs2, "comment_reply"):
                await insert_notification(
                    conn,
                    parent_comment_author_uid,
                    "comment_reply",
                    {
                        "video_id": video_id,
                        "video_title": video_title[:120],
                        "comment_id": comment_id,
                        "actor_uid": actor_uid,
                        "text_preview": text_preview,
                    },
                )
    finally:
        await release_conn(conn)

async def _handle_comment_reply(payload: Dict[str, Any]):
    await _handle_comment_created(payload)

async def _handle_comment_voted(payload: Dict[str, Any]):
    # Agregate likes to Redis, meta: author and video_id
    if payload.get("vote") != 1:
        return
    comment_id = payload.get("comment_id")
    comment_author_uid = payload.get("comment_author_uid")
    actor_uid = payload.get("actor_uid")
    video_id = payload.get("video_id")
    if not comment_id or not comment_author_uid or not actor_uid:
        return
    if comment_author_uid == actor_uid:
        return

    window_start = int(
        datetime.utcnow().timestamp()
        // notifications_config.LIKES_BATCH_WINDOW_SEC
        * notifications_config.LIKES_BATCH_WINDOW_SEC
    )
    key = f"{LIKE_PREFIX}:{comment_id}:{window_start}"
    r = _redis()
    try:
        await r.sadd(key, actor_uid)
        await r.expire(key, notifications_config.LIKES_BATCH_WINDOW_SEC * 4)
        await r.set(f"{key}:author", comment_author_uid, ex=notifications_config.LIKES_BATCH_WINDOW_SEC * 4)
        if video_id:
            await r.set(f"{key}:video_id", video_id, ex=notifications_config.LIKES_BATCH_WINDOW_SEC * 4)
    finally:
        await _redis_close(r)

@celery_app.task(name="notifications.flush_like_batches")
def flush_like_batches():
    _run(_flush_like_batches())


async def _flush_like_batches():
    r = _redis()
    try:
        cursor = 0
        to_process: List[str] = []
        pattern = f"{LIKE_PREFIX}:*"
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
            for k in keys:
                if k.endswith(":author") or k.endswith(":video_id"):
                    continue
                to_process.append(k)
            if cursor == 0:
                break

        if not to_process:
            return

        conn = await get_conn()
        try:
            for key in to_process:
                members = await r.smembers(key)
                author = await r.get(f"{key}:author")
                video_id = await r.get(f"{key}:video_id")
                if not author or not members:
                    continue

                prefs = await _load_prefs(conn, author)
                if not await _should_send(prefs, "comment_liked_batch"):
                    continue

                parts = key.split(":")
                comment_id = parts[2] if len(parts) >= 3 else None
                if not comment_id:
                    continue

                video_title = ""
                if video_id:
                    v = await get_video(conn, video_id)
                    if v and v.get("title"):
                        video_title = v["title"]

                likers_list = sorted(members)

                dedupe_key = f"comment_liked_batch:{author}:{comment_id}:{parts[-1]}"
                payload = {
                    "comment_id": comment_id,
                    "likers": likers_list,
                    "like_count": len(likers_list),
                    "video_id": video_id,
                    "video_title": (video_title or "")[:120],
                }
                await insert_notification(
                    conn,
                    author,
                    "comment_liked_batch",
                    payload,
                    agg_key=comment_id,
                    dedupe_key=dedupe_key,
                )
                await r.delete(key)
                await r.delete(f"{key}:author")
                await r.delete(f"{key}:video_id")
        finally:
            await release_conn(conn)
    finally:
        await _redis_close(r)


async def _handle_video_published(payload: Dict[str, Any]):
    video_id = payload.get("video_id")
    author_uid = payload.get("author_uid")
    status = payload.get("status")
    processing_status = payload.get("processing_status")
    is_unlisted = bool(payload.get("is_unlisted"))
    if not video_id or not author_uid:
        return
    if status != "public" or processing_status != "ready":
        return

    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT subscriber_uid FROM subscriptions
            WHERE channel_uid = $1
            """,
            author_uid,
        )
        if not rows:
            return
        title = (payload.get("title") or "")[:notifications_config.MAX_PAYLOAD_PREVIEW_LEN]
        for r in rows:
            subscriber = r["subscriber_uid"]
            if not subscriber or subscriber == author_uid:
                continue
            prefs = await _load_prefs(conn, subscriber)
            allow_unlisted_global = notifications_config.ALLOW_UNLISTED_SUBS_NOTIFICATIONS
            if not await _should_send(
                prefs,
                "video_published",
                is_unlisted=is_unlisted,
                allow_unlisted=allow_unlisted_global,
            ):
                continue
            await insert_notification(
                conn,
                subscriber,
                "video_published",
                {
                    "video_id": video_id,
                    "author_uid": author_uid,
                    "title": title,
                    "is_unlisted": is_unlisted,
                },
            )
    finally:
        await release_conn(conn)