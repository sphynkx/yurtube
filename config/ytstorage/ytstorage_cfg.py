"""
ytstorage configuration (single source of truth).

gRPC (required):
- YTSTORAGE_GRPC_ADDRESS: host:port
- YTSTORAGE_GRPC_TLS: "true"/"false"
- YTSTORAGE_GRPC_TOKEN: optional bearer token
- YTSTORAGE_BASE_PREFIX: optional logical prefix (server-side namespace)
- YTSTORAGE_GRPC_MAX_MSG_MB: max gRPC message size in MB

Public URL (optional):
- YTSTORAGE_PUBLIC_BASE_URL: if set, build_storage_url may use it (currently app serves via /internal/storage/file/* anyway)
"""

import os

# ---- gRPC canonical env vars ----
YTSTORAGE_GRPC_ADDRESS: str = os.getenv("YTSTORAGE_GRPC_ADDRESS", "127.0.0.1:9092").strip()
YTSTORAGE_GRPC_TLS: bool = (os.getenv("YTSTORAGE_GRPC_TLS", "").strip().lower() in ("1", "true", "yes", "on"))
YTSTORAGE_GRPC_TOKEN: str = os.getenv("YTSTORAGE_GRPC_TOKEN", "").strip()
YTSTORAGE_BASE_PREFIX: str = os.getenv("YTSTORAGE_BASE_PREFIX", "").strip()

try:
    YTSTORAGE_GRPC_MAX_MSG_MB: int = int(os.getenv("YTSTORAGE_GRPC_MAX_MSG_MB", "64").strip())
except Exception:
    YTSTORAGE_GRPC_MAX_MSG_MB = 64

# ---- optional public URL base (kept for future; not required for current /internal/storage/file/* serving) ----
YTSTORAGE_PUBLIC_BASE_URL: str = os.getenv("YTSTORAGE_PUBLIC_BASE_URL", "").strip()