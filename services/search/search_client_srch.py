from typing import Optional

from services.search.settings_srch import settings
from services.search.backends.base_srch import BaseSearchBackend
from services.search.backends.manticore_srch import ManticoreBackend
from services.search.backends.postgres_srch import PostgresBackend

_backend: Optional[BaseSearchBackend] = None

def get_backend() -> BaseSearchBackend:
    global _backend
    if _backend is not None:
        return _backend
    # Graceful selection: prefer configured backend, but ensure no 500 on downtime.
    # If BACKEND is manticore, use ManticoreBackend which now returns [] on network failures.
    # If BACKEND is postgres, use PostgresBackend.
    if settings.BACKEND == "manticore":
        _backend = ManticoreBackend()
    else:
        _backend = PostgresBackend()
    return _backend