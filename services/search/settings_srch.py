import os
from dataclasses import dataclass

@dataclass(frozen=True)
class SearchSettings:
    # Which search backend to use for app-level search API:
    # - "postgres"
    # - "manticore"
    BACKEND: str = os.getenv("SEARCH_BACKEND", "postgres").strip().lower()

    # Manticore connection (used when BACKEND="manticore" or for indexing transport below)
    MANTICORE_HOST: str = os.getenv("MANTICORE_HOST", "127.0.0.1")
    MANTICORE_HTTP_PORT: int = int(os.getenv("MANTICORE_HTTP_PORT", "9308"))
    MANTICORE_INDEX_VIDEOS: str = os.getenv("MANTICORE_INDEX_VIDEOS", "videos_rt")
    MANTICORE_INDEX_SUBTITLES: str = os.getenv("MANTICORE_INDEX_SUBTITLES", "subtitles_rt")

    # PostgreSQL FTS/tuning
    PG_DEFAULT_TS_LANG: str = os.getenv("PG_DEFAULT_TS_LANG", "russian")
    PG_TS_CONFIG: str = os.getenv("PG_TS_CONFIG", "yt_multi")
    TRGM_THRESHOLD: str = os.getenv("TRGM_THRESHOLD", "0.15")

    # Transport abstraction for index execution layer used by Manticore backend:
    # SEARCH_INDEX_TRANSPORT selects how db/search_manticore_db.py will execute queries:
    # - "manticore_http": direct HTTP to Manticore (default), optional CLI fallback
    # - "service_http": call external indexing service (microservice) via HTTP
    # SEARCH_INDEX_SERVICE_URL is required when using "service_http", for example:
    #   SEARCH_INDEX_SERVICE_URL=http://indexer.internal:8080
    SEARCH_INDEX_TRANSPORT: str = os.getenv("SEARCH_INDEX_TRANSPORT", "manticore_http").strip().lower()
    SEARCH_INDEX_SERVICE_URL: str = os.getenv("SEARCH_INDEX_SERVICE_URL", "").strip()

settings = SearchSettings()