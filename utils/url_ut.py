from typing import Optional

from config.config import settings


def build_storage_url(rel_path: str) -> str:
    """
    Convert a storage-relative path (e.g., 'ab/abc123/thumbs/thumb_default.jpg')
    into a public URL, using STORAGE_PUBLIC_BASE_URL if provided, otherwise /storage/.
    """
    base: Optional[str] = settings.STORAGE_PUBLIC_BASE_URL
    path = rel_path.lstrip("/")
    if base:
        return f"{base.rstrip('/')}/{path}"
    return f"/storage/{path}"