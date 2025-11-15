"""
Lightweight event publisher abstraction.
Future: swap broker (RabbitMQ, etc.) by changing Celery config only.
"""
from typing import Dict, Any, Optional
from services.notifications.celery_app import celery_app

# Generic publish (fire-and-forget)
def publish(event_name: str, payload: Dict[str, Any], idempotency_key: Optional[str] = None) -> None:
    """
    event_name: e.g. comment.created, comment.reply, comment.voted, video.published
    payload: small JSON dict
    idempotency_key: optional (not enforced in MVP, reserved)
    """
    body = {
        "event": event_name,
        "payload": payload,
        "idempotency_key": idempotency_key,
    }
    celery_app.send_task("notifications.handle_event", args=[body], queue="notify_immediate")

