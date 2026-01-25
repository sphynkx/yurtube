from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from utils.ytconvert.sizeparse_ut import parse_size_bytes
from utils.ytconvert.ytconvert_servers_ut import YtconvertServer, parse_servers


@dataclass(frozen=True)
class YtconvertClientConfig:
    servers: List[YtconvertServer]
    chunk_bytes: int
    upload_timeout_sec: float
    grpc_plaintext: bool


def load_ytconvert_config() -> YtconvertClientConfig:
    raw_servers = (os.environ.get("YTCONVERT_SERVERS") or "").strip()
    servers = parse_servers(raw_servers)

    chunk_bytes = parse_size_bytes(os.environ.get("YTCONVERT_CHUNK_BYTES", ""), default=4 * 1024 * 1024)

    try:
        upload_timeout_sec = float((os.environ.get("YTCONVERT_UPLOAD_TIMEOUT_SEC") or "600").strip() or "600")
    except Exception:
        upload_timeout_sec = 600.0

    grpc_plaintext = (os.environ.get("YTCONVERT_GRPC_PLAINTEXT", "true").strip().lower() in ("1", "true", "yes", "on"))

    return YtconvertClientConfig(
        servers=servers,
        chunk_bytes=chunk_bytes,
        upload_timeout_sec=upload_timeout_sec,
        grpc_plaintext=grpc_plaintext,
    )