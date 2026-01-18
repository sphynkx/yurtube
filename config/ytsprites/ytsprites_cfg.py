# For client side which working with external ytsprites service
import os

def ytsprites_address() -> str:
    return os.getenv("YTSPRITES_GRPC_ADDR", "127.0.0.1:9094")

YTSPRITES_TOKEN: str = os.getenv("YTSPRITES_TOKEN", "")

YTSPRITES_SUBMIT_TIMEOUT: float = float(os.getenv("YTSPRITES_SUBMIT_TIMEOUT", "120.0"))
YTSPRITES_STATUS_TIMEOUT: float = float(os.getenv("YTSPRITES_STATUS_TIMEOUT", "1800.0"))
YTSPRITES_RESULT_TIMEOUT: float = float(os.getenv("YTSPRITES_RESULT_TIMEOUT", "1200.0"))

# Overhead gPRC'z default 4Mb
# On service side need to set same limits!!
YTSPRITES_MAX_UPLOAD_BYTES: int = int(os.getenv("YTSPRITES_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))  # 512MB

# MIME default
YTSPRITES_DEFAULT_MIME: str = os.getenv("YTSPRITES_DEFAULT_MIME", "video/webm")

# Options for send to ytsprites service
YTSPRITES_SPRITE_STEP_SEC: float = float(os.getenv("YTSPRITES_SPRITE_STEP_SEC", "2.0"))
YTSPRITES_SPRITE_COLS: int = int(os.getenv("YTSPRITES_SPRITE_COLS", "10"))
YTSPRITES_SPRITE_ROWS: int = int(os.getenv("YTSPRITES_SPRITE_ROWS", "10"))
YTSPRITES_SPRITE_FORMAT: str = os.getenv("YTSPRITES_SPRITE_FORMAT", "jpg")
YTSPRITES_SPRITE_QUALITY: int = int(os.getenv("YTSPRITES_SPRITE_QUALITY", "85"))

# Where to store result
APP_STORAGE_FS_ROOT: str = os.getenv("APP_STORAGE_FS_ROOT", "/var/www/yurtube/storage")
APP_STORAGE_WEB_PREFIX: str = os.getenv("APP_STORAGE_WEB_PREFIX", "/storage")

# gRPC limits and compression
YTSPRITES_GRPC_MAX_SEND_MB: int = int(os.getenv("YTSPRITES_GRPC_MAX_SEND_MB", "512"))   # send limit
YTSPRITES_GRPC_MAX_RECV_MB: int = int(os.getenv("YTSPRITES_GRPC_MAX_RECV_MB", "512"))   # receive limit
YTSPRITES_GRPC_COMPRESSION: str = os.getenv("YTSPRITES_GRPC_COMPRESSION", "gzip")