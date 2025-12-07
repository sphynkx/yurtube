"""
Build storage client based on three sources (priority order):
1) Explicit 'kind' argument from main.py
2) Environment variable (STORAGE_PROVIDER)
3) Module-level config constants in:
   - config.storage.storage_remote_cfg
   - config.storage.storage_cfg

Local storage root is resolved from APP_STORAGE_FS_ROOT
"""
import os
import importlib
from typing import Optional
from services.storage.base_srv import StorageClient
from services.storage.local_srv import LocalStorageClient  # type: ignore
from services.storage.remote_srv import RemoteStorageClient


def _env_str(key: str) -> str:
    val = os.getenv(key)
    return val.strip() if isinstance(val, str) else ""


def _mod_attr(mod_name: str, attr: str) -> Optional[str]:
    # Try to import a module and read its top-level variable
    try:
        mod = importlib.import_module(mod_name)
        v = getattr(mod, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    return None


def _resolve_backend_kind(kind: str) -> str:
    # 1. explicit arg
    if isinstance(kind, str) and kind.strip():
        return kind.strip().lower()

    # 2. environment
    sp = _env_str("STORAGE_PROVIDER")
    if sp:
        return sp.lower()

    # 3. module-level config constants
    spm = _mod_attr("config.storage.storage_remote_cfg", "STORAGE_PROVIDER")
    if spm:
        return spm.lower()

    # default
    return "local"


def _resolve_local_abs_root() -> str:
    app_root = _env_str("APP_STORAGE_FS_ROOT")
    if app_root:
        return app_root

    app_root_mod = _mod_attr("config.storage.storage_cfg", "APP_STORAGE_FS_ROOT")
    if app_root_mod:
        return app_root_mod

    raise RuntimeError("LocalStorageClient requires APP_STORAGE_FS_ROOT")


def build_storage_client(kind: str) -> StorageClient:
    """
    Returns LocalStorageClient or RemoteStorageClient, based on resolved backend kind.
    """
    k = _resolve_backend_kind(kind)

    if k == "remote":
        return RemoteStorageClient()

    abs_root = _resolve_local_abs_root()
    return LocalStorageClient(abs_root=abs_root)