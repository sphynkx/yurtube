# For client side which working with external ytsprites service
# Service generates sprites and VTT for received video. Replacement of ytms service. Logic is same.

import os

def ytsprites_address() -> str:
    return os.getenv("YTSPRITES_GRPC_ADDR", "127.0.0.1:60051")

YTSPRITES_TOKEN: str = os.getenv("YTSPRITES_TOKEN", "")

YTSPRITES_SUBMIT_TIMEOUT: float = float(os.getenv("YTSPRITES_SUBMIT_TIMEOUT", "120.0"))
YTSPRITES_STATUS_TIMEOUT: float = float(os.getenv("YTSPRITES_STATUS_TIMEOUT", "1800.0"))
YTSPRITES_RESULT_TIMEOUT: float = float(os.getenv("YTSPRITES_RESULT_TIMEOUT", "1200.0"))

YTSPRITES_MAX_UPLOAD_BYTES: int = int(os.getenv("YTSPRITES_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))  # 512MB

YTSPRITES_DEFAULT_MIME: str = os.getenv("YTSPRITES_DEFAULT_MIME", "video/webm")

YTSPRITES_SPRITE_STEP_SEC: float = float(os.getenv("YTSPRITES_SPRITE_STEP_SEC", "10.0"))
YTSPRITES_SPRITE_COLS: int = int(os.getenv("YTSPRITES_SPRITE_COLS", "5"))
YTSPRITES_SPRITE_ROWS: int = int(os.getenv("YTSPRITES_SPRITE_ROWS", "5"))
YTSPRITES_SPRITE_FORMAT: str = os.getenv("YTSPRITES_SPRITE_FORMAT", "jpg")
YTSPRITES_SPRITE_QUALITY: int = int(os.getenv("YTSPRITES_SPRITE_QUALITY", "85"))