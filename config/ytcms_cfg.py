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

# Audio pre-processing before sending to service:
# Dont send full video  - audio only. Good for big videos..
# YTCMS_AUDIO_PREPROCESS: enable feature | stream copy | recode to low format (off | demux | transcode)
# YTCMS_AUDIO_CODEC: format for transcode (mp3 | opus | aac | flac | wav)
# YTCMS_AUDIO_SR: int Hz (default 16000)
# YTCMS_AUDIO_CHANNELS: 1 or 2 (default 1)
# YTCMS_AUDIO_BITRATE: ffmpeg bitrate string, e.g. "48k"
YTCMS_AUDIO_PREPROCESS = (os.getenv("YTCMS_AUDIO_PREPROCESS", "off") or "off").strip().lower()
YTCMS_AUDIO_CODEC = (os.getenv("YTCMS_AUDIO_CODEC", "AAC") or "AAC").strip().lower()
YTCMS_AUDIO_SR = int(os.getenv("YTCMS_AUDIO_SR", "16000"))
YTCMS_AUDIO_CHANNELS = int(os.getenv("YTCMS_AUDIO_CHANNELS", "1"))
YTCMS_AUDIO_BITRATE = os.getenv("YTCMS_AUDIO_BITRATE", "96k")


def ytcms_address() -> str:
    return f"{YTCMS_HOST}:{YTCMS_PORT}"