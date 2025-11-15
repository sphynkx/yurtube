from typing import Any, Dict
from services.notifications.celery_app import celery_app

def publish(event: str, payload: Dict[str, Any]) -> None:
    """
    Publish event to notification pipeline.
    """
    celery_app.send_task(
        "notifications.handle_event",
        args=[{"event": event, "payload": payload}],
        queue="notify_immediate",
        ignore_result=True,
    )