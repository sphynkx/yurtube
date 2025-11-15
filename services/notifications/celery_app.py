import celery
from celery.schedules import schedule
from config.notifications_config import notifications_config

celery_app = celery.Celery(
    "notifications",
    broker=notifications_config.broker(),
    backend=notifications_config.backend(),
    include=["services.notifications.tasks"],
)

celery_app.conf.update(
    task_default_queue="notify_immediate",
    task_routes={
        "notifications.handle_event": {"queue": "notify_immediate"},
        "notifications.flush_like_batches": {"queue": "notify_batch"},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=False,
    task_time_limit=60,
    beat_schedule={
        "flush-like-batches-every-window": {
            "task": "notifications.flush_like_batches",
            "schedule": schedule(notifications_config.LIKES_BATCH_WINDOW_SEC),
        }
    },
)