import os

# Base URL of YTMS (thumbnails) service
YTMS_BASE_URL: str = os.getenv("YTMS_BASE_URL", "http://127.0.0.1:8089")

# Shared secret for HMAC signature (used both for job auth_token and callback verification)
YTMS_CALLBACK_SECRET: str = os.getenv("YTMS_CALLBACK_SECRET", "dev-secret")

# Base URL of this app (to build callback URL)
APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8077")

# Filesystem root of storage and its web prefix (to compute web path for stored assets)
STORAGE_FS_ROOT: str = os.getenv("STORAGE_FS_ROOT", "/var/www/storage")
STORAGE_WEB_PREFIX: str = os.getenv("STORAGE_WEB_PREFIX", "/storage")