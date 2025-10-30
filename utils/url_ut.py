from typing import Optional

from config.config import settings


def build_storage_url(rel_path: str) -> str:
    base: Optional[str] = settings.STORAGE_PUBLIC_BASE_URL
    path = rel_path.lstrip("/")
    if base:
        return f"{base.rstrip('/')}/{path}"
    return f"/storage/{path}"