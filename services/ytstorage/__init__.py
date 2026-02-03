from __future__ import annotations
import os
from typing import Literal

# DEPRECATE local provider!!
##from services.ytstorage.local_srv import LocalStorageClient
from services.ytstorage.base_srv import StorageClient


def build_storage_client(kind: Literal["local"] = "local") -> StorageClient:
    """
    Client storage fabric (for now - local only).
    Further kinds: "remote", "overlay".
    """
# DEPRECATE local provider!!
#    if kind == "local":
#        root = os.getenv("APP_STORAGE_FS_ROOT", "/var/www/yurtube/storage")
#        return LocalStorageClient(abs_root=root)
    raise ValueError(f"Unsupported storage kind: {kind}")