from __future__ import annotations
import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default


@dataclass
class GrpcConfig:
    """
    Parameters:
    - host: interface on which the application listens (default 0.0.0.0).
    - port: gRPC port (default 9090).
    - tls_*: future-proof
    """
    host: str = os.getenv("APP_GRPC_HOST", "0.0.0.0")
    port: int = _get_int("APP_GRPC_PORT", 9090)

    tls_enabled: bool = False
    tls_ca_path: str | None = None
    tls_cert_path: str | None = None
    tls_key_path: str | None = None


def load_grpc_config() -> GrpcConfig:
    return GrpcConfig()