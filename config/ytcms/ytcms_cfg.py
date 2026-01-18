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

    # IPv6 in brackets: [::1]:9099
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
class YTCMSServer:
    host: str
    port: int

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"


def parse_ytcms_servers_env(val: Optional[str]) -> List[YTCMSServer]:
    """
    YTCMS_SERVERS format:
      host1:port1,host2:port2,[ipv6]:port3

    No token per-server for now. Auth token is global (YTCMS_TOKEN).
    """
    raw = (val or "").strip()
    if not raw:
        return []

    default_host = os.getenv("YTCMS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    default_port = _parse_int(os.getenv("YTCMS_PORT", "9099"), 9099)

    out: List[YTCMSServer] = []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        host, port = _parse_server_addr(p, default_host, default_port)
        out.append(YTCMSServer(host=host, port=port))
    return out


@dataclass
class YTCMSConfig:
    # ytcms conf (legacy single-server env, kept for backward compatibility)
    host: str = os.getenv("YTCMS_HOST", "127.0.0.1")
    port: int = int(os.getenv("YTCMS_PORT", "9099"))
    token: str = os.getenv("YTCMS_TOKEN", "CHANGE_ME")

    # New multi-server list (preferred order)
    servers: List[YTCMSServer] = None  # type: ignore

    # Default transcribe params
    default_lang: str = os.getenv("YTCMS_DEFAULT_LANG", "auto")
    default_task: str = os.getenv("YTCMS_DEFAULT_TASK", "transcribe")

    # Timeouts to prevent DEADLINE_EXCEEDED/UNAVAILABLE events from service
    poll_interval: float = float(os.getenv("YTCMS_POLL_INTERVAL", "1.5"))
    submit_timeout: float = float(os.getenv("YTCMS_SUBMIT_TIMEOUT", "1800.0"))
    status_timeout: float = float(os.getenv("YTCMS_STATUS_TIMEOUT", "30.0"))
    result_timeout: float = float(os.getenv("YTCMS_RESULT_TIMEOUT", "30.0"))


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


def load_ytcms_config() -> YTCMSConfig:
    cfg = YTCMSConfig()
    servers = parse_ytcms_servers_env(os.getenv("YTCMS_SERVERS"))
    if servers:
        cfg.servers = servers
        # keep legacy fields pointing to preferred first server
        cfg.host = servers[0].host
        cfg.port = servers[0].port
    else:
        cfg.servers = [YTCMSServer(host=cfg.host, port=cfg.port)]
    return cfg


def ytcms_address() -> str:
    # Backward compatible function (used in some places)
    cfg = load_ytcms_config()
    return f"{cfg.host}:{cfg.port}"


# Backward-compatible legacy globals (used by some code paths)
_cfg = load_ytcms_config()
YTCMS_HOST = _cfg.host
YTCMS_PORT = _cfg.port
YTCMS_TOKEN = _cfg.token
YTCMS_DEFAULT_LANG = _cfg.default_lang
YTCMS_DEFAULT_TASK = _cfg.default_task
YTCMS_POLL_INTERVAL = _cfg.poll_interval
YTCMS_SUBMIT_TIMEOUT = _cfg.submit_timeout
YTCMS_STATUS_TIMEOUT = _cfg.status_timeout
YTCMS_RESULT_TIMEOUT = _cfg.result_timeout