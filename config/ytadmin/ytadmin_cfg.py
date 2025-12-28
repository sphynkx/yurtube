from __future__ import annotations
import os
from dataclasses import dataclass
from typing import List, Optional


def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default


@dataclass
class YTAdminConfig:
    enabled: bool = _get_bool("YTADMIN_ENABLED", False)

    host: str = os.getenv("YTADMIN_HOST", "127.0.0.1")
    port: int = _get_int("YTADMIN_PORT", 50051)

    token: Optional[str] = os.getenv("YTADMIN_TOKEN") or None

    tls_ca_path: Optional[str] = os.getenv("YTADMIN_TLS_CA") or None
    tls_cert_path: Optional[str] = os.getenv("YTADMIN_TLS_CERT") or None
    tls_key_path: Optional[str] = os.getenv("YTADMIN_TLS_KEY") or None

    service_name: str = os.getenv("SERVICE_NAME", "yurtube-app")
    instance_id: str = os.getenv("SERVICE_INSTANCE_ID", "")
    version: str = os.getenv("SERVICE_VERSION", "")

    push_health_interval_sec: int = _get_int("YTADMIN_HEALTH_INTERVAL_SEC", 30)
    push_effconf_interval_sec: int = _get_int("YTADMIN_EFFCONF_INTERVAL_SEC", 300)

    effconf_enable: bool = _get_bool("YTADMIN_EFFCONF_ENABLE", True)
    effconf_whitelist: List[str] = (
        os.getenv("YTADMIN_EFFCONF_WHITELIST", "APP_MODE,DEBUG,DB_HOST,DB_PORT,DB_NAME,DB_USER,REDIS_HOST,REDIS_PORT")
        .split(",")
        if os.getenv("YTADMIN_EFFCONF_WHITELIST")
        else ["APP_MODE", "DEBUG", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "REDIS_HOST", "REDIS_PORT"]
    )
    # List of masking keys (secrets)
    effconf_redact_keys: List[str] = (
        os.getenv("YTADMIN_EFFCONF_REDACT", "SECRET_KEY,DB_PASSWORD,REDIS_PASSWORD,JWT_SECRET,API_KEY")
        .split(",")
        if os.getenv("YTADMIN_EFFCONF_REDACT")
        else ["SECRET_KEY", "DB_PASSWORD", "REDIS_PASSWORD", "JWT_SECRET", "API_KEY"]
    )


def load_config() -> YTAdminConfig:
    return YTAdminConfig()