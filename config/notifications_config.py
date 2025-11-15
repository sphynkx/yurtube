from dataclasses import dataclass
import os

@dataclass
class NotificationsConfig:
    ENABLED: bool = True

    REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_NOTIF_DB", "2"))

    BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "")
    RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "")

    # Fall back to redis URLs if not explicitly set
    def broker(self) -> str:
        if self.BROKER_URL:
            return self.BROKER_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def backend(self) -> str:
        if self.RESULT_BACKEND:
            return self.RESULT_BACKEND
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    LIKES_BATCH_WINDOW_SEC: int = 300  # 5 minutes
    ALLOW_UNLISTED_SUBS_NOTIFICATIONS: bool = True  # global toggle
    MAX_PAYLOAD_PREVIEW_LEN: int = 160

    # Default prefs if user has no row
    DEFAULT_INAPP: dict = None
    DEFAULT_EMAIL: dict = None

    def __post_init__(self):
        self.DEFAULT_INAPP = {
            "comment_created": True,
            "comment_reply": True,
            "comment_liked_batch": True,
            "video_published": True,
        }
        self.DEFAULT_EMAIL = {
            "comment_created": False,
            "comment_reply": False,
            "comment_liked_batch": False,
            "video_published": False,
        }

notifications_config = NotificationsConfig()