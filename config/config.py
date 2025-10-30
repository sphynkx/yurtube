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

    STORAGE_ROOT: str = _getenv_required("STORAGE_ROOT")
    STORAGE_PUBLIC_BASE_URL: Optional[str] = os.getenv("STORAGE_PUBLIC_BASE_URL", None)

    BASE_URL: Optional[str] = os.getenv("BASE_URL", None)
    DEBUG: bool = _getenv_bool("DEBUG", False)


settings = Settings()