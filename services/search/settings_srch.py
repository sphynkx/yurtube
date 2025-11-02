import os
from dataclasses import dataclass

@dataclass(frozen=True)
class SearchSettings:
    BACKEND: str = os.getenv("SEARCH_BACKEND", "postgres").strip().lower()
    MANTICORE_HOST: str = os.getenv("MANTICORE_HOST", "127.0.0.1")
    MANTICORE_HTTP_PORT: int = int(os.getenv("MANTICORE_HTTP_PORT", "9308"))
    MANTICORE_INDEX_VIDEOS: str = os.getenv("MANTICORE_INDEX_VIDEOS", "videos_rt")
    MANTICORE_INDEX_SUBTITLES: str = os.getenv("MANTICORE_INDEX_SUBTITLES", "subtitles_rt")
    PG_DEFAULT_TS_LANG: str = os.getenv("PG_DEFAULT_TS_LANG", "russian")
    # New:
    PG_TS_CONFIG: str = os.getenv("PG_TS_CONFIG", "yt_multi")
    TRGM_THRESHOLD: str = os.getenv("TRGM_THRESHOLD", "0.15")

settings = SearchSettings()