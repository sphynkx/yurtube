import logging
import asyncio
from typing import Any, Dict, List
from datetime import datetime

from redis.asyncio import Redis as RedisClient

from services.notifications.celery_app import celery_app
from config.notifications_config import notifications_config
from db import get_conn, release_conn
from db.notifications_db import insert_notification, get_user_prefs
from db.videos_db import get_video, get_video_min

logger = logging.getLogger("notifications")

LIKE_PREFIX = "notif:likes:agg"
VIDEO_LIKE_PREFIX = "notif:video_likes:agg"

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

def _run(coro):
    return _loop.run_until_complete(coro)

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
    if not getattr(notifications_config, "ENABLED", True):
        logger.info("Notifications globally disabled; skip handle_event")
        return
    event = (body or {}).get("event")
    payload = (body or {}).get("payload") or {}
    logger.info("Handle event=%s payload=%s", event, payload)
    if event == "comment.created":
        _run(_handle_comment_created(payload))
    elif event == "comment.reply":
        _run(_handle_comment_reply(payload))
    elif event == "comment.voted":
        _run(_handle_comment_voted(payload))
    elif event == "video.published":
        _run(_handle_video_published(payload))
    elif event == "video.reacted":
        _run(_handle_video_reacted(payload))
    else:
        logger.info("Unknown event=%s (ignored)", event)

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

async def _should_send(
    prefs: Dict[str, Dict[str, Any]],
    notif_type: str,
    is_unlisted: bool = False,
    allow_unlisted: bool = True,
) -> bool:
    p = prefs.get(notif_type)
    if not p:
        return True
    if not p.get("inapp", True):
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
        logger.warning("comment.created missing fields video_id=%s actor=%s cid=%s", video_id, actor_uid, comment_id)
        return
    conn = await get_conn()
    try:
        v = await get_video(conn, video_id)
        if not v:
            logger.info("Video not found for comment.created video_id=%s", video_id)
            return
        video_author = v.get("author_uid")
        video_title = v.get("title") or ""
        if video_author and video_author != actor_uid:
            prefs = await _load_prefs(conn, video_author)
            if await _should_send(prefs, "comment_created"):
                notif_id = await insert_notification(
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
                logger.info("Notification comment_created -> %s notif_id=%s", video_author, notif_id)
        if parent_comment_author_uid and parent_comment_author_uid not in (actor_uid, video_author):
            prefs2 = await _load_prefs(conn, parent_comment_author_uid)
            if await _should_send(prefs2, "comment_reply"):
                notif_id2 = await insert_notification(
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
                logger.info("Notification comment_reply -> %s notif_id=%s", parent_comment_author_uid, notif_id2)
    finally:
        await release_conn(conn)

async def _handle_comment_reply(payload: Dict[str, Any]):
    await _handle_comment_created(payload)

async def _handle_comment_voted(payload: Dict[str, Any]):
    if payload.get("vote") != 1:
        logger.info("Skip comment.voted (vote=%s not 1)", payload.get("vote"))
        return
    comment_id = payload.get("comment_id")
    comment_author_uid = payload.get("comment_author_uid")
    actor_uid = payload.get("actor_uid")
    video_id = payload.get("video_id")
    if not comment_id or not comment_author_uid or not actor_uid:
        logger.warning("comment.voted missing fields cid=%s author=%s actor=%s", comment_id, comment_author_uid, actor_uid)
        return
    if comment_author_uid == actor_uid:
        logger.info("Skip comment.voted (self-like) cid=%s", comment_id)
        return
    w = notifications_config.LIKES_BATCH_WINDOW_SEC
    window_start = int(datetime.utcnow().timestamp() // w * w)
    key = f"{LIKE_PREFIX}:{comment_id}:{window_start}"
    r = _redis()
    try:
        added = await r.sadd(key, actor_uid)
        await r.expire(key, w * 4)
        await r.set(f"{key}:author", comment_author_uid, ex=w * 4)
        if video_id:
            await r.set(f"{key}:video_id", video_id, ex=w * 4)
        logger.info("Comment like aggregated key=%s added=%s actor=%s", key, added, actor_uid)
    finally:
        await _redis_close(r)

@celery_app.task(name="notifications.flush_like_batches")
def flush_like_batches():
    if not getattr(notifications_config, "ENABLED", True):
        logger.info("Notifications disabled; skip flush_like_batches")
        return
    logger.info("Flush comment like batches start")
    _run(_flush_like_batches())
    logger.info("Flush comment like batches end")

async def _flush_like_batches():
    r = _redis()
    try:
        cursor = 0
        to_process: List[str] = []
        pattern = f"{LIKE_PREFIX}:*"
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=pattern, count=200)
            for k in keys:
                if k.endswith(":author") or k.endswith(":video_id"):
                    continue
                to_process.append(k)
            if cursor == 0:
                break
        logger.info("Comment like flush found %d keys", len(to_process))
        if not to_process:
            return
        conn = await get_conn()
        try:
            for key in to_process:
                members = await r.smembers(key)
                author = await r.get(f"{key}:author")
                video_id = await r.get(f"{key}:video_id")
                logger.info("Process comment like batch key=%s members=%s author=%s video_id=%s",
                            key, members, author, video_id)
                if not author or not members:
                    await r.delete(key)
                    await r.delete(f"{key}:author")
                    if video_id:
                        await r.delete(f"{key}:video_id")
                    continue
                prefs = await _load_prefs(conn, author)
                if not await _should_send(prefs, "comment_liked_batch"):
                    logger.info("Prefs deny comment_liked_batch author=%s", author)
                    await r.delete(key)
                    await r.delete(f"{key}:author")
                    if video_id:
                        await r.delete(f"{key}:video_id")
                    continue
                parts = key.split(":")
                comment_id_from_key = parts[-2] if len(parts) >= 2 else None
                if not comment_id_from_key:
                    logger.warning("Invalid batch key format for comments: %s", key)
                    await r.delete(key)
                    await r.delete(f"{key}:author")
                    if video_id:
                        await r.delete(f"{key}:video_id")
                    continue
                video_title = ""
                if video_id:
                    v = await get_video(conn, video_id)
                    if v and v.get("title"):
                        video_title = v["title"]
                likers_list = sorted(members)
                window_bucket = parts[-1] if len(parts) >= 1 else ""
                dedupe_key = f"comment_liked_batch:{author}:{comment_id_from_key}:{window_bucket}"
                payload = {
                    "comment_id": comment_id_from_key,
                    "likers": likers_list,
                    "like_count": len(likers_list),
                    "video_id": video_id,
                    "video_title": (video_title or "")[:120],
                }
                notif_id = await insert_notification(
                    conn,
                    author,
                    "comment_liked_batch",
                    payload,
                    agg_key=comment_id_from_key,
                    dedupe_key=dedupe_key,
                )
                logger.info("Inserted comment_liked_batch notif_id=%s author=%s comment=%s like_count=%d",
                            notif_id, author, comment_id_from_key, len(likers_list))
                await r.delete(key)
                await r.delete(f"{key}:author")
                if video_id:
                    await r.delete(f"{key}:video_id")
        finally:
            await release_conn(conn)
    finally:
        await _redis_close(r)

async def _handle_video_reacted(payload: Dict[str, Any]):
    reaction = str(payload.get("reaction") or "").lower()
    if reaction != "like":
        logger.info("Skip video.reacted (reaction=%s not like)", reaction)
        return
    actor_uid = payload.get("actor_uid")
    video_author_uid = payload.get("video_author_uid")
    video_id = payload.get("video_id")
    title = (payload.get("title") or "")[:notifications_config.MAX_PAYLOAD_PREVIEW_LEN]
    if not (actor_uid and video_author_uid and video_id):
        logger.warning("video.reacted missing fields actor=%s author=%s vid=%s", actor_uid, video_author_uid, video_id)
        return
    if actor_uid == video_author_uid:
        logger.info("Skip video.reacted (author liked own video) video_id=%s", video_id)
        return
    w = getattr(notifications_config, "VIDEO_LIKES_BATCH_WINDOW_SEC", notifications_config.LIKES_BATCH_WINDOW_SEC)
    if not isinstance(w, int) or w <= 0:
        logger.error("Invalid VIDEO_LIKES_BATCH_WINDOW_SEC=%s", w)
        return
    window_start = int(datetime.utcnow().timestamp() // w * w)
    key = f"{VIDEO_LIKE_PREFIX}:{video_id}:{window_start}"
    r = _redis()
    try:
        added = await r.sadd(key, actor_uid)
        await r.expire(key, w * 4)
        await r.set(f"{key}:author", video_author_uid, ex=w * 4)
        await r.set(f"{key}:title", title, ex=w * 4)
        logger.info("Video like aggregated key=%s added=%s actor=%s title='%s'", key, added, actor_uid, title)
    finally:
        await _redis_close(r)

@celery_app.task(name="notifications.flush_video_like_batches")
def flush_video_like_batches():
    if not getattr(notifications_config, "ENABLED", True):
        logger.info("Notifications disabled; skip flush_video_like_batches")
        return
    logger.info("Flush video like batches start")
    _run(_flush_video_like_batches())
    logger.info("Flush video like batches end")

async def _flush_video_like_batches():
    r = _redis()
    try:
        cursor = 0
        to_process: List[str] = []
        pattern = f"{VIDEO_LIKE_PREFIX}:*"
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=pattern, count=200)
            base_keys = [k for k in keys if not (k.endswith(":author") or k.endswith(":title"))]
            to_process.extend(base_keys)
            if cursor == 0:
                break
        logger.info("Video like flush found %d keys", len(to_process))
        if not to_process:
            return
        conn = await get_conn()
        try:
            for key in to_process:
                members = await r.smembers(key)
                author = await r.get(f"{key}:author")
                title = await r.get(f"{key}:title") or ""
                logger.info("Process video like batch key=%s members=%s author=%s title='%s'",
                            key, members, author, title)
                if not author or not members:
                    await r.delete(key)
                    await r.delete(f"{key}:author")
                    await r.delete(f"{key}:title")
                    continue
                parts = key.split(":")
                video_id_from_key = parts[-2] if len(parts) >= 2 else None
                if not video_id_from_key:
                    logger.warning("Invalid batch key format for videos: %s", key)
                    await r.delete(key)
                    await r.delete(f"{key}:author")
                    await r.delete(f"{key}:title")
                    continue
                vrow = await get_video_min(conn, video_id_from_key)
                if not vrow:
                    logger.info("Video missing for batch key=%s cleanup", key)
                    await r.delete(key)
                    await r.delete(f"{key}:author")
                    await r.delete(f"{key}:title")
                    continue
                final_title = title or (vrow["title"] or "")
                prefs = await _load_prefs(conn, author)
                if not await _should_send(prefs, "video_liked_batch"):
                    logger.info("Prefs deny video_liked_batch author=%s video=%s", author, video_id_from_key)
                    await r.delete(key)
                    await r.delete(f"{key}:author")
                    await r.delete(f"{key}:title")
                    continue
                likers_list = sorted(members)
                window_bucket = parts[-1] if len(parts) >= 1 else ""
                dedupe_key = f"video_liked_batch:{author}:{video_id_from_key}:{window_bucket}"
                payload = {
                    "video_id": video_id_from_key,
                    "video_title": final_title[:120],
                    "likers": likers_list,
                    "like_count": len(likers_list),
                }
                notif_id = await insert_notification(
                    conn,
                    author,
                    "video_liked_batch",
                    payload,
                    agg_key=video_id_from_key,
                    dedupe_key=dedupe_key,
                )
                logger.info(
                    "Inserted video_liked_batch notif_id=%s author=%s video=%s like_count=%d",
                    notif_id, author, video_id_from_key, len(likers_list)
                )
                await r.delete(key)
                await r.delete(f"{key}:author")
                await r.delete(f"{key}:title")
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
        logger.warning("video.published missing fields video_id=%s author=%s", video_id, author_uid)
        return
    if status != "public" or processing_status != "ready":
        logger.info("Skip video_published (status=%s processing=%s)", status, processing_status)
        return
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            "SELECT subscriber_uid FROM subscriptions WHERE channel_uid = $1",
            author_uid,
        )
        if not rows:
            logger.info("No subscribers for author=%s", author_uid)
            return
        title = (payload.get("title") or "")[:notifications_config.MAX_PAYLOAD_PREVIEW_LEN]
        allow_unlisted_global = notifications_config.ALLOW_UNLISTED_SUBS_NOTIFICATIONS
        for r in rows:
            subscriber = r["subscriber_uid"]
            if not subscriber or subscriber == author_uid:
                continue
            prefs = await _load_prefs(conn, subscriber)
            if not await _should_send(
                prefs,
                "video_published",
                is_unlisted=is_unlisted,
                allow_unlisted=allow_unlisted_global,
            ):
                continue
            notif_id = await insert_notification(
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
            logger.info("Inserted video_published notif_id=%s subscriber=%s video=%s", notif_id, subscriber, video_id)
    finally:
        await release_conn(conn)