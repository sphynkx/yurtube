## SRTG_DONE
## SRTG_2MODIFY: STORAGE_
## SRTG_2MODIFY: build_storage_url(
## SRTG_2MODIFY: storage/
## SRTG_2MODIFY: _path
## May be deprecated in future
from typing import Optional

from config.config import settings


def build_storage_url(rel_path: str) -> str:
    """
    Build a public URL for a storage-relative path.
    During migration, this remains the single place to change URL strategy:
    - If STORAGE_PUBLIC_BASE_URL is set, it will be used as the base.
    - Otherwise, it falls back to the local mount /storage.
    Note: rel_path should be storage-relative (no leading /storage).
    """
    base: Optional[str] = settings.STORAGE_PUBLIC_BASE_URL
    path = (rel_path or "").lstrip("/")
    if base:
        return f"{base.rstrip('/')}/{path}"
    return f"/storage/{path}"