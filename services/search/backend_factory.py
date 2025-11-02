import os
from typing import Protocol

from services.search.settings_srch import settings

# Backends
from services.search.backends.manticore_srch import ManticoreBackend  # existing
from services.search.backends.postgres_srch import PostgresBackend


class SearchBackend(Protocol):
    async def search_videos(self, q: str, limit: int, offset: int): ...
    async def suggest_titles(self, prefix: str, limit: int = 10): ...
    async def index_video(self, video): ...
    async def delete_video(self, video_id: str): ...


_backend_singleton: SearchBackend | None = None


def get_search_backend() -> SearchBackend:
    global _backend_singleton
    if _backend_singleton is not None:
        return _backend_singleton

    backend_key = (getattr(settings, "SEARCH_BACKEND", None) or os.getenv("SEARCH_BACKEND") or "manticore").lower()
    if backend_key in ("pg", "postgres", "postgresql"):
        _backend_singleton = PostgresBackend()
    else:
        _backend_singleton = ManticoreBackend()
    return _backend_singleton