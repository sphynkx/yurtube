# For client side which working with external ytsprites service
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


def _parse_int(val: str, default_int: int) -> int:
    try:
        n = int(str(val).strip())
        return n if n > 0 else default_int
    except Exception:
        return default_int


def _parse_server_addr(raw: str, default_host: str, default_port: int) -> tuple[str, int]:
    """
    Parse address part into (host, port).
    Supports:
      - host:port
      - [ipv6]:port
      - host (port default)
    """
    s = (raw or "").strip()
    if not s:
        return default_host, default_port

    # IPv6 in brackets: [::1]:9094
    if s.startswith("["):
        rb = s.find("]")
        if rb > 0:
            host = s[1:rb].strip() or default_host
            rest = s[rb + 1 :].strip()
            if rest.startswith(":"):
                port = _parse_int(rest[1:], default_port)
                return host, port
            return host, default_port

    # host:port (split on last colon; IPv6 must be bracketed)
    if ":" in s:
        host, port_s = s.rsplit(":", 1)
        host = host.strip() or default_host
        port = _parse_int(port_s, default_port)
        return host, port

    return s, default_port


@dataclass(frozen=True)
class YTSpritesServer:
    host: str
    port: int

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"


def parse_ytsprites_servers_env(val: Optional[str]) -> List[YTSpritesServer]:
    """
    YTSPRITES_SERVERS format:
      host1:port1,host2:port2,[ipv6]:port3

    If missing -> fallback to YTSPRITES_GRPC_ADDR or default 127.0.0.1:9094
    """
    raw = (val or "").strip()
    if not raw:
        return []

    default_addr = os.getenv("YTSPRITES_GRPC_ADDR", "127.0.0.1:9094").strip() or "127.0.0.1:9094"
    default_host, default_port = _parse_server_addr(default_addr, "127.0.0.1", 9094)

    out: List[YTSpritesServer] = []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        host, port = _parse_server_addr(p, default_host, default_port)
        out.append(YTSpritesServer(host=host, port=port))
    return out


def ytsprites_address() -> str:
    # legacy single-address accessor (used by older code)
    return os.getenv("YTSPRITES_GRPC_ADDR", "127.0.0.1:9094")


def ytsprites_servers() -> List[YTSpritesServer]:
    """
    Preferred server list (new). Falls back to legacy YTSPRITES_GRPC_ADDR.
    """
    servers = parse_ytsprites_servers_env(os.getenv("YTSPRITES_SERVERS"))
    if servers:
        return servers

    addr = ytsprites_address()
    host, port = _parse_server_addr(addr, "127.0.0.1", 9094)
    return [YTSpritesServer(host=host, port=port)]


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
YTSPRITES_GRPC_MAX_SEND_MB: int = int(os.getenv("YTSPRITES_GRPC_MAX_SEND_MB", "512"))  # send limit
YTSPRITES_GRPC_MAX_RECV_MB: int = int(os.getenv("YTSPRITES_GRPC_MAX_RECV_MB", "512"))  # receive limit
YTSPRITES_GRPC_COMPRESSION: str = os.getenv("YTSPRITES_GRPC_COMPRESSION", "gzip")

# Failover tuning
YTSPRITES_HEALTH_TIMEOUT: float = float(os.getenv("YTSPRITES_HEALTH_TIMEOUT", "2.0"))
YTSPRITES_SERVER_TTL: float = float(os.getenv("YTSPRITES_SERVER_TTL", "10"))