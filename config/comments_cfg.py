from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class CommentsSettings(BaseSettings):
    # Mongo connection
    MONGO_HOST: str = "127.0.0.1"
    MONGO_PORT: int = 27017
    MONGO_DB_NAME: str = "yt_comments"
    MONGO_USER: str = "yt_user"
    MONGO_PASSWORD: str = ""
    MONGO_AUTH_SOURCE: str = "yt_comments"

    COMMENTS_ENABLED: bool = True

    # Tree config
    COMMENTS_MAX_DEPTH: int = 6
    COMMENTS_MAX_CHILDREN_INLINE: int = 3
    COMMENT_MAX_LEN: int = 1000

    # Size limits (bytes)
    COMMENTS_SOFT_CHUNK_LIMIT_BYTES: int = 14_000_000
    COMMENTS_HARD_DOC_LIMIT_BYTES: int = 16_000_000
    COMMENTS_SOFT_ROOT_LIMIT_BYTES: int = 12_000_000  # Notification threshold

    # Content policy
    COMMENTS_STOP_WORDS: List[str] = []
    COMMENTS_ALLOW_TIME_LINKS: bool = True

    # Visibility
    COMMENTS_SHOW_HIDDEN_FOR_OWNER: bool = True

    # Snapshot mode (future)
    COMMENTS_SNAPSHOT_MODE: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


comments_settings = CommentsSettings()