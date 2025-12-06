import os

# Storage types: local | remote | overlay (на будущее)
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")

# Local storage root (for LocalStorageClient)
APP_STORAGE_FS_ROOT = os.getenv("APP_STORAGE_FS_ROOT", "/var/www/yurtube/storage")