import os

# ytcms conf
YTCMS_HOST = os.getenv("YTCMS_HOST", "127.0.0.1")
YTCMS_PORT = int(os.getenv("YTCMS_PORT", "9099"))
YTCMS_TOKEN = os.getenv("YTCMS_TOKEN", "CHANGE_ME")

# Default transcribe params
YTCMS_DEFAULT_LANG = os.getenv("YTCMS_DEFAULT_LANG", "auto")
YTCMS_DEFAULT_TASK = os.getenv("YTCMS_DEFAULT_TASK", "transcribe")

def ytcms_address() -> str:
    return f"{YTCMS_HOST}:{YTCMS_PORT}"