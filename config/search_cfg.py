import os

SEARCH_BACKEND = os.getenv("SEARCH_BACKEND", "postgres").strip().lower()
MANTICORE_HOST = os.getenv("MANTICORE_HOST", "127.0.0.1")
MANTICORE_HTTP_PORT = int(os.getenv("MANTICORE_HTTP_PORT", "9308"))
MANTICORE_INDEX_VIDEOS = os.getenv("MANTICORE_INDEX_VIDEOS", "videos_rt")
MANTICORE_INDEX_SUBTITLES = os.getenv("MANTICORE_INDEX_SUBTITLES", "subtitles_rt")
PG_DEFAULT_TS_LANG = os.getenv("PG_DEFAULT_TS_LANG", "russian")
