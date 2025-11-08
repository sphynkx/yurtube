import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


def _getenv_required(key: str) -> str:
    val = os.getenv(key)
    if val is None or val == "":
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


def _getenv_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or val == "":
        return default
    return int(val)


def _getenv_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None or val == "":
        return default
    return val.lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = _getenv_int("APP_PORT", 8077)

    DATABASE_URL: str = _getenv_required("DATABASE_URL")

    SECRET_KEY: str = _getenv_required("SECRET_KEY")
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "ytsid")
    SESSION_TTL_SECONDS: int = _getenv_int("SESSION_TTL_SECONDS", 1209600)
    SESSION_COOKIE_SECURE: bool = _getenv_bool("SESSION_COOKIE_SECURE", True)

    PASSWORD_MIN_SCORE: int = _getenv_int("PASSWORD_MIN_SCORE", 2)

    GOOGLE_OAUTH_DEBUG=1
    GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    GOOGLE_OAUTH_REDIRECT_URL = os.getenv("GOOGLE_OAUTH_REDIRECT_URL", "")
    GOOGLE_ALLOWED_DOMAINS = os.getenv("GOOGLE_ALLOWED_DOMAINS", "")

    STORAGE_ROOT: str = _getenv_required("STORAGE_ROOT")
    STORAGE_PUBLIC_BASE_URL: Optional[str] = os.getenv("STORAGE_PUBLIC_BASE_URL", None)

    BASE_URL: Optional[str] = os.getenv("BASE_URL", None)
    DEBUG: bool = _getenv_bool("DEBUG", False)

    # Video editing defaults
    EDIT_UI_ENABLED: bool = _getenv_bool("EDIT_UI_ENABLED", True)
    DEFAULT_RENDITION_PRESETS: str = os.getenv("DEFAULT_RENDITION_PRESETS", "1080p,720p,480p,360p")
    DEFAULT_RENDITION_CODEC: str = os.getenv("DEFAULT_RENDITION_CODEC", "vp9")

    # Embed defaults (applied to new videos unless overridden)
    EMBED_DEFAULT_AUTOPLAY: int = _getenv_int("EMBED_DEFAULT_AUTOPLAY", 0)
    EMBED_DEFAULT_MUTE: int = _getenv_int("EMBED_DEFAULT_MUTE", 0)
    EMBED_DEFAULT_LOOP: int = _getenv_int("EMBED_DEFAULT_LOOP", 0)
    VIDEO_PLAYER: str = os.getenv("VIDEO_PLAYER", "yurtube").strip() or "yurtube"

    # Fallback placeholder for not-found videos (static/anim. images).
    FALLBACK_PLACEHOLDER_URL: str = os.getenv(
        "FALLBACK_PLACEHOLDER_URL",
        "static/img/fallback_video_notfound.gif",
    )

    # Brand assets
    BRAND_LOGO_URL: str = os.getenv("BRAND_LOGO_URL", "/static/img/YT_long.png")
    FAVICON_URL: str = os.getenv("FAVICON_URL", "/static/img/YT_fav32.png")
    APPLE_TOUCH_ICON_URL: str = os.getenv("APPLE_TOUCH_ICON_URL", "/static/img/YT_fav128.png")

    # Right-bar recommendations (tunable; safe defaults)
    RIGHTBAR_ENABLED: bool = _getenv_bool("RIGHTBAR_ENABLED", True)
    RIGHTBAR_LIMIT: int = _getenv_int("RIGHTBAR_LIMIT", 10)  # default increased to 10
    # Characteristic time for freshness decay (in days)
    RIGHTBAR_TAU_DAYS: int = _getenv_int("RIGHTBAR_TAU_DAYS", 7)
    # Max number of search results to consider for text-similarity source
    RIGHTBAR_SEARCH_TAKE: int = _getenv_int("RIGHTBAR_SEARCH_TAKE", 50)
    # Quotas for top-10 diversification
    RIGHTBAR_MAX_SAME_AUTHOR_TOP10: int = _getenv_int("RIGHTBAR_MAX_SAME_AUTHOR_TOP10", 3)
    RIGHTBAR_MAX_SAME_CATEGORY_TOP10: int = _getenv_int("RIGHTBAR_MAX_SAME_CATEGORY_TOP10", 6)

settings = Settings()