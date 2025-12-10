"""
Local storage configuration.
- APP_STORAGE_FS_ROOT: absolute filesystem path to storage root
- STORAGE_PUBLIC_BASE_URL: optional public URL base (served by nginx or app)
"""

import os

# Preferred local storage root (used by LocalStorageClient)
APP_STORAGE_FS_ROOT: str = os.getenv("APP_STORAGE_FS_ROOT", "/var/www/yurtube/storage").strip()

# Optional public URL base
STORAGE_PUBLIC_BASE_URL: str = os.getenv("STORAGE_PUBLIC_BASE_URL", "").strip()