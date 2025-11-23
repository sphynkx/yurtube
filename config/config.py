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
    ## Disable built-in "/docs", "/redoc", "openapi.json"
    API_DOCS_ENABLED = False
    API_404_REDIRECT_ENABLED: bool = _getenv_bool("API_404_REDIRECT_ENABLED", True)

    CSRF_ENFORCE: bool = _getenv_bool("CSRF_ENFORCE", True)
    CSRF_COOKIE_NAME: str = os.getenv("CSRF_COOKIE_NAME", "yt_csrf")
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "ytsid")

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
    BRAND_TAGLINE: str = os.getenv("BRAND_TAGLINE", "")

    # Right-bar recommendations (tunable; safe defaults)
    RIGHTBAR_ENABLED: bool = _getenv_bool("RIGHTBAR_ENABLED", True)
    RIGHTBAR_LIMIT: int = _getenv_int("RIGHTBAR_LIMIT", 10)
    RIGHTBAR_TAU_DAYS: int = _getenv_int("RIGHTBAR_TAU_DAYS", 7)
    RIGHTBAR_SEARCH_TAKE: int = _getenv_int("RIGHTBAR_SEARCH_TAKE", 50)
    RIGHTBAR_MAX_SAME_AUTHOR_TOP10: int = _getenv_int("RIGHTBAR_MAX_SAME_AUTHOR_TOP10", 3)
    RIGHTBAR_MAX_SAME_CATEGORY_TOP10: int = _getenv_int("RIGHTBAR_MAX_SAME_CATEGORY_TOP10", 6)

    # Twitter OAuth 2.0
    TWITTER_OAUTH_CLIENT_ID: str = os.getenv("TWITTER_OAUTH_CLIENT_ID", "")
    TWITTER_OAUTH_CLIENT_SECRET: str = os.getenv("TWITTER_OAUTH_CLIENT_SECRET", "")
    TWITTER_OAUTH_REDIRECT_URL: str = os.getenv("TWITTER_OAUTH_REDIRECT_URL", "")
    TWITTER_OAUTH_SCOPES: str = os.getenv("TWITTER_OAUTH_SCOPES", "")
    TWITTER_OAUTH_DEBUG: bool = _getenv_bool("TWITTER_OAUTH_DEBUG", False)
    TWITTER_ENABLE_OIDC: bool = _getenv_bool("TWITTER_ENABLE_OIDC", False)

    # Optional pseudo-email when provider does not supply email
    TWITTER_ALLOW_PSEUDO_EMAIL: bool = _getenv_bool("TWITTER_ALLOW_PSEUDO_EMAIL", True)
    PSEUDO_EMAIL_DOMAIN: str = os.getenv("PSEUDO_EMAIL_DOMAIN", "twitter.local")

    # Auto-linking policy
    AUTO_LINK_GOOGLE_BY_EMAIL: bool = _getenv_bool("AUTO_LINK_GOOGLE_BY_EMAIL", True)

    # Sprites control for video upload process
    AUTO_SPRITES_ENABLED = True
    AUTO_SPRITES_MIN_DURATION = 3

    AUTO_CAPTIONS_MIN_DURATION = 3
    AUTO_CAPTIONS_ENABLED = False
    AUTO_CAPTIONS_LANG = "auto"

settings = Settings()