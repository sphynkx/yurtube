from __future__ import annotations

import re
from typing import Any, Dict, Optional

import grpc

from services.ytadmin.ytadmin_proto import info_pb2, info_pb2_grpc
from services.ytcms.ytcms_client_srv import pick_ytcms_server_addr


_HOSTPORT_RE = re.compile(r"^\s*(\[[^\]]+\]|[^:]+)\s*:\s*(\d+)\s*$")


def _parse_host_port(target: str) -> tuple[str, int]:
    t = (target or "").strip()
    m = _HOSTPORT_RE.match(t)
    if not m:
        raise ValueError(f"invalid target: {target!r}")
    host = m.group(1).strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    port = int(m.group(2))
    return host, port


def _is_bad_advertised_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("0.0.0.0", "127.0.0.1", "::", "::1", "localhost")


def _try_parse_resp_host(resp_hostport: str) -> Optional[tuple[str, int]]:
    s = (resp_hostport or "").strip()
    if not s:
        return None
    try:
        h, p = _parse_host_port(s)
        if _is_bad_advertised_host(h):
            return None
        return h, p
    except Exception:
        return None


def get_active_server(timeout_sec: float = 1.0) -> Dict[str, Any]:
    """
    Returns basic identity of the currently active YTCMS server.

    Active server is resolved using the same health/failover logic as the client:
      services.ytcms.ytcms_client_srv.pick_ytcms_server_addr()

    Then queries grpc.health.v1.Info/All to extract:
      {
        "host": "IP",          # prefer addr we connected to (NOT bind 0.0.0.0)
        "port": 9099,
        "model": "version_or_model_name",
        "app_name": "...",
        "instance_id": "..."
      }

    Notes:
    - Uses synchronous grpc channel.
    - If Info/All fails, still returns host/port based on chosen addr.
    """
    addr = pick_ytcms_server_addr()
    host, port = _parse_host_port(addr)

    channel = None
    try:
        channel = grpc.insecure_channel(addr)
        stub = info_pb2_grpc.InfoStub(channel)
        resp = stub.All(info_pb2.InfoRequest(selector=""), timeout=timeout_sec)

        # Prefer the *connected* address for host/port. Only override if service advertises a real reachable host.
        resp_hostport = (getattr(resp, "host", "") or "").strip()
        parsed = _try_parse_resp_host(resp_hostport)
        if parsed:
            host, port = parsed

        model = (getattr(resp, "version", None) or "").strip() or ""

        return {
            "host": host,
            "port": port,
            "model": model,
            "app_name": getattr(resp, "app_name", "") or "",
            "instance_id": getattr(resp, "instance_id", "") or "",
        }
    except Exception:
        return {"host": host, "port": port, "model": "", "app_name": "", "instance_id": ""}
    finally:
        try:
            if channel is not None:
                channel.close()
        except Exception:
            pass