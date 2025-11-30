from dataclasses import dataclass
import os

@dataclass
class NotificationsConfig:
    # Global notification flag
    ENABLED: bool = True

    # Redis for notifications
    REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_NOTIF_DB", "2"))

    # Real broker/BE URLs Celery
    BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "")
    RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "")

    # Aggregation windows
    LIKES_BATCH_WINDOW_SEC: int = int(os.getenv("LIKES_BATCH_WINDOW_SEC", "30"))  # was 300
    VIDEO_LIKES_BATCH_WINDOW_SEC: int = 0

    ALLOW_UNLISTED_SUBS_NOTIFICATIONS: bool = True
    MAX_PAYLOAD_PREVIEW_LEN: int = 160

    DEFAULT_INAPP: dict = None
    DEFAULT_EMAIL: dict = None

    def broker(self) -> str:
        if self.BROKER_URL:
            return self.BROKER_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def backend(self) -> str:
        if self.RESULT_BACKEND:
            return self.RESULT_BACKEND
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def __post_init__(self):
        # win for reatcts for videos: from .env VIDEO_LIKES_BATCH_WINDOW_SEC or as for comments
        env_video = (os.getenv("VIDEO_LIKES_BATCH_WINDOW_SEC") or "").strip()
        try:
            v = int(env_video) if env_video else 0
        except Exception:
            v = 0
        self.VIDEO_LIKES_BATCH_WINDOW_SEC = v if v > 0 else self.LIKES_BATCH_WINDOW_SEC

        self.DEFAULT_INAPP = {
            "comment_created": True,
            "comment_reply": True,
            "comment_liked_batch": True,
            "video_published": True,
            "video_liked_batch": True,
        }
        self.DEFAULT_EMAIL = {
            "comment_created": False,
            "comment_reply": False,
            "comment_liked_batch": False,
            "video_published": False,
            "video_liked_batch": False,
        }

notifications_config = NotificationsConfig()