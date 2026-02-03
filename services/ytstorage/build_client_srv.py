"""
Storage client builder.

DEPRECATION NOTICE:
- Local storage mode and STORAGE_PROVIDER switching are deprecated.
- The application assumes remote ytstorage gRPC is always used.
"""

from services.ytstorage.base_srv import StorageClient
from services.ytstorage.remote_srv import RemoteStorageClient


def build_storage_client(kind: str = "") -> StorageClient:
    """
    Return RemoteStorageClient unconditionally.
    The 'kind' argument is ignored and kept only for backward compatibility.
    """
    return RemoteStorageClient()