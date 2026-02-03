from __future__ import annotations

# Public surface for ytstorage package.
# Storage is remote-only now.

from services.ytstorage.base_srv import StorageClient
from services.ytstorage.build_client_srv import build_storage_client

__all__ = [
    "StorageClient",
    "build_storage_client",
]