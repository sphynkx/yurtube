"""
Local storage configuration.
- APP_STORAGE_FS_ROOT: absolute filesystem path to storage root
- STORAGE_PUBLIC_BASE_URL: optional public URL base (served by nginx or app)
"""

import os

# Preferred local storage root (used by LocalStorageClient)
APP_STORAGE_FS_ROOT = os.getenv("APP_STORAGE_FS_ROOT", "/var/www/yurtube/storage")

# Optional public URL base (e.g., when served via nginx)
STORAGE_PUBLIC_BASE_URL = os.getenv("STORAGE_PUBLIC_BASE_URL", "")