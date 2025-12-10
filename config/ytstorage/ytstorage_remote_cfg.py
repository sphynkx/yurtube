"""
Remote storage configuration.
- STORAGE_PROVIDER: "local" | "remote"
- STORAGE_REMOTE_ADDRESS: gRPC server address
- STORAGE_REMOTE_TLS: enable TLS for gRPC channel
- STORAGE_REMOTE_TOKEN: bearer token passed in gRPC metadata
- STORAGE_REMOTE_BASE_PREFIX: logical prefix for paths if server expects base dir
- STORAGE_GRPC_MAX_MSG_MB: gRPC max message size in MB
"""

import os

STORAGE_PROVIDER: str = os.getenv("STORAGE_PROVIDER", "local").strip()

STORAGE_REMOTE_ADDRESS: str = os.getenv("STORAGE_REMOTE_ADDRESS", "127.0.0.1:50070").strip()
STORAGE_REMOTE_TLS: bool = (os.getenv("STORAGE_REMOTE_TLS", "").strip().lower() in ("1", "true", "yes", "on"))
STORAGE_REMOTE_TOKEN: str = os.getenv("STORAGE_REMOTE_TOKEN", "").strip()
STORAGE_REMOTE_BASE_PREFIX: str = os.getenv("STORAGE_REMOTE_BASE_PREFIX", "").strip()
# Max message size (MB)
try:
    STORAGE_GRPC_MAX_MSG_MB: int = int(os.getenv("STORAGE_GRPC_MAX_MSG_MB", "64").strip())
except Exception:
    STORAGE_GRPC_MAX_MSG_MB = 64