from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass
class YTTransConfig:
    """
    Configuration for the yttrans (translation) service client.
    """
    host: str = os.getenv("YTTRANS_HOST", "127.0.0.1")
    port: int = int(os.getenv("YTTRANS_PORT", "9095"))
    # TLS is disabled for MVP
    tls_enabled: bool = False
    token: str | None = os.getenv("YTTRANS_TOKEN") or None


def load_yttrans_config() -> YTTransConfig:
    return YTTransConfig()