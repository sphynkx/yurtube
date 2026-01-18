from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Optional


def _get_bool(name: str, default: bool = False) -> bool:
    """
    Safely reads a boolean from environment variable `name`.
    Accepts: 1/true/yes/y/on (case-insensitive). Returns `default` if unset.
    """
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _get_int(name: str, default: int) -> int:
    """
    Safely reads an integer from environment variable `name`.
    Returns `default` if unset or parsing fails.
    """
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default


DEFAULT_WHITELIST = [
    "APP_MODE", "DEBUG",
    "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER",
    "REDIS_HOST", "REDIS_PORT",
]
DEFAULT_REDACT = [
    "SECRET_KEY", "DB_PASSWORD", "REDIS_PASSWORD", "JWT_SECRET", "API_KEY",
]


def _env_list(name: str, default_values: List[str]) -> List[str]:
    """
    Returns a list parsed from env var `name` (comma-separated).
    If not set, returns a copy of `default_values`.
    Values are stripped; empty entries are removed.
    """
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return list(default_values)  # copy to avoid shared mutable state
    return [s.strip() for s in str(v).split(",") if s.strip()]


def _default_effconf_whitelist() -> List[str]:
    """
    Default factory for effconf_whitelist: reads from env or uses DEFAULT_WHITELIST.
    """
    return _env_list("YTADMIN_EFFCONF_WHITELIST", DEFAULT_WHITELIST)


def _default_effconf_redact() -> List[str]:
    """
    Default factory for effconf_redact_keys: reads from env or uses DEFAULT_REDACT.
    """
    return _env_list("YTADMIN_EFFCONF_REDACT", DEFAULT_REDACT)


@dataclass
class YTAdminConfig:
    """
    Configuration for the admin push client (AdminIngest).
    This config is also used to build the ServiceIdentity for pull-side AppProbe.
    """
    enabled: bool = _get_bool("YTADMIN_ENABLED", False)

    # Admin ingest target (gRPC) — where we push health/effconf
    host: str = os.getenv("YTADMIN_HOST", "127.0.0.1")
    port: int = _get_int("YTADMIN_PORT", 50052)

    # Auth token (short-lived preferred). Sent as metadata: Authorization: Bearer <token>
    token: Optional[str] = os.getenv("YTADMIN_TOKEN") or None

    # TLS (optional for ingest)
    tls_ca_path: Optional[str] = os.getenv("YTADMIN_TLS_CA") or None
    tls_cert_path: Optional[str] = os.getenv("YTADMIN_TLS_CERT") or None
    tls_key_path: Optional[str] = os.getenv("YTADMIN_TLS_KEY") or None

    # Application identity (for both push and pull AppProbe/GetIdentity)
    service_name: str = os.getenv("SERVICE_NAME", "YurTube")
    instance_id: str = os.getenv("SERVICE_INSTANCE_ID", "")  # e.g., hostname/pod
    version: str = os.getenv("SERVICE_VERSION", "")

    # Public address of the app itself (shown to admin in identity.host)
    identity_host: str = os.getenv("YTADMIN_IDENTITY_HOST", "127.0.0.1:9090")

    # Push intervals
    push_health_interval_sec: int = _get_int("YTADMIN_HEALTH_INTERVAL_SEC", 30)
    push_effconf_interval_sec: int = _get_int("YTADMIN_EFFCONF_INTERVAL_SEC", 300)

    # Effective config collection
    effconf_enable: bool = _get_bool("YTADMIN_EFFCONF_ENABLE", True)
    effconf_whitelist: List[str] = field(default_factory=_default_effconf_whitelist)
    effconf_redact_keys: List[str] = field(default_factory=_default_effconf_redact)


def load_config() -> YTAdminConfig:
    """
    Constructs and returns YTAdminConfig with values sourced from environment.
    """
    return YTAdminConfig()