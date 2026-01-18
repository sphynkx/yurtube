from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class YTTransServer:
    host: str
    port: int
    token: Optional[str] = None

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"


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

    # IPv6 in brackets: [::1]:9095
    if s.startswith("["):
        rb = s.find("]")
        if rb > 0:
            host = s[1:rb].strip() or default_host
            rest = s[rb + 1 :].strip()
            if rest.startswith(":"):
                port = _parse_int(rest[1:], default_port)
                return host, port
            return host, default_port

    # host:port (split on last colon to keep hostnames like "a:b" out; IPv6 must be bracketed)
    if ":" in s:
        host, port_s = s.rsplit(":", 1)
        host = host.strip() or default_host
        port = _parse_int(port_s, default_port)
        return host, port

    return s, default_port


def parse_yttrans_servers_env(val: Optional[str]) -> List[YTTransServer]:
    """
    YTTRANS_SERVERS format (recommended):
      host:port@token,host2:port2,[ipv6]:port3@token3

    Token part is optional. Use '@' as separator because ':' conflicts with IPv6.
    """
    raw = (val or "").strip()
    if not raw:
        return []

    default_host = os.getenv("YTTRANS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    default_port = _parse_int(os.getenv("YTTRANS_PORT", "9095"), 9095)

    out: List[YTTransServer] = []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        addr = p
        token: Optional[str] = None

        if "@" in p:
            addr, tok = p.split("@", 1)
            tok = tok.strip()
            token = tok or None

        host, port = _parse_server_addr(addr.strip(), default_host, default_port)
        out.append(YTTransServer(host=host, port=port, token=token))

    return out


@dataclass
class YTTransConfig:
    """
    Configuration for the yttrans (translation) service client.

    Backward compatible:
      - If YTTRANS_SERVERS is set, it is used.
      - Otherwise falls back to YTTRANS_HOST/YTTRANS_PORT/YTTRANS_TOKEN.
    """
    # legacy single-target settings (still filled for compatibility)
    host: str = os.getenv("YTTRANS_HOST", "127.0.0.1")
    port: int = int(os.getenv("YTTRANS_PORT", "9095"))
    tls_enabled: bool = False
    token: str | None = os.getenv("YTTRANS_TOKEN") or None

    # new multi-server list
    servers: List[YTTransServer] = None  # type: ignore


def load_yttrans_config() -> YTTransConfig:
    cfg = YTTransConfig()

    servers = parse_yttrans_servers_env(os.getenv("YTTRANS_SERVERS"))
    if servers:
        cfg.servers = servers
        # keep legacy fields pointing to "preferred" first server
        cfg.host = servers[0].host
        cfg.port = servers[0].port
        cfg.token = servers[0].token
    else:
        cfg.servers = [YTTransServer(host=cfg.host, port=cfg.port, token=cfg.token)]

    return cfg