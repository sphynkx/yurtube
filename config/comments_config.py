from typing import List, Optional

# Support for Pydantic v2 (pydantic-settings) with fallback to v1
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # Pydantic v2
    _USE_V2 = True
except ImportError:
    from pydantic import BaseSettings  # Pydantic v1
    SettingsConfigDict = None
    _USE_V2 = False

from pydantic import Field


class CommentsSettings(BaseSettings):
    # Mongo connection
    MONGO_HOST: str = Field(default="127.0.0.1")
    MONGO_PORT: int = Field(default=27017)
    MONGO_DB_NAME: str = Field(default="yt_comments")
    MONGO_USER: Optional[str] = None
    MONGO_PASSWORD: Optional[str] = None
    MONGO_AUTH_SOURCE: Optional[str] = "admin"

    COMMENTS_ENABLED: bool = True

    # Tree config
    COMMENTS_MAX_DEPTH: int = 6
    COMMENTS_MAX_CHILDREN_INLINE: int = 3
    COMMENT_MAX_LEN: int = 1000

    # Size limits (bytes)
    COMMENTS_SOFT_CHUNK_LIMIT_BYTES: int = 14_000_000
    COMMENTS_HARD_DOC_LIMIT_BYTES: int = 16_000_000
    COMMENTS_SOFT_ROOT_LIMIT_BYTES: int = 12_000_000  # Notify threshold

    # Content policy
    COMMENTS_STOP_WORDS: List[str] = []
    COMMENTS_ALLOW_TIME_LINKS: bool = True

    # Visibility
    COMMENTS_SHOW_HIDDEN_FOR_OWNER: bool = True

    # Snapshot mode (future)
    COMMENTS_SNAPSHOT_MODE: bool = False

    if _USE_V2:
        # Pydantic v2 style
        model_config = SettingsConfigDict(
            env_file=".env",
            case_sensitive=False,
            extra="ignore",
        )
    else:
        # Pydantic v1 style
        class Config:
            env_file = ".env"
            case_sensitive = False
            extra = "ignore"


comments_settings = CommentsSettings()