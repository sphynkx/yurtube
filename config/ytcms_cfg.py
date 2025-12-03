import os

# ytcms conf
YTCMS_HOST = os.getenv("YTCMS_HOST", "127.0.0.1")
YTCMS_PORT = int(os.getenv("YTCMS_PORT", "9099"))
YTCMS_TOKEN = os.getenv("YTCMS_TOKEN", "CHANGE_ME")

# Default transcribe params
YTCMS_DEFAULT_LANG = os.getenv("YTCMS_DEFAULT_LANG", "auto")
YTCMS_DEFAULT_TASK = os.getenv("YTCMS_DEFAULT_TASK", "transcribe")

# Timeouts to prevent DEADLINE_EXCEEDED/UNAVAILABLE events from service
YTCMS_POLL_INTERVAL = float(os.getenv("YTCMS_POLL_INTERVAL", "1.5"))
YTCMS_SUBMIT_TIMEOUT = float(os.getenv("YTCMS_SUBMIT_TIMEOUT", "1800.0"))
YTCMS_STATUS_TIMEOUT = float(os.getenv("YTCMS_STATUS_TIMEOUT", "30.0"))
YTCMS_RESULT_TIMEOUT = float(os.getenv("YTCMS_RESULT_TIMEOUT", "30.0"))

def ytcms_address() -> str:
    return f"{YTCMS_HOST}:{YTCMS_PORT}"