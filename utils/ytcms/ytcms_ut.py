from __future__ import annotations

import json

import re
from typing import Any, Dict, Optional

import grpc

from services.ytadmin.ytadmin_proto import info_pb2, info_pb2_grpc
from services.ytcms.ytcms_client_srv import pick_ytcms_server_addr, open_channel, split_addr


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


def _parse_diarization_models(labels: Dict[str, Any]) -> tuple[list, str]:
    """Info label "diarization_models" is a JSON list [{"id","title","threshold","default"}]. Never raises."""
    default_id = str(labels.get("diarization_default_model") or "").strip()
    out: list = []
    try:
        raw = json.loads(labels.get("diarization_models") or "[]")
        if isinstance(raw, list):
            for m in raw:
                if isinstance(m, dict) and str(m.get("id") or "").strip():
                    mid = str(m["id"]).strip()
                    out.append({"id": mid, "title": str(m.get("title") or mid), "default": mid == default_id})
    except Exception:
        out = []
    return out, default_id


def get_active_cms_server(timeout_sec: float = 1.0) -> Dict[str, Any]:
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
    host, port = _parse_host_port(split_addr(addr)[0])

    channel = None
    try:
        channel = open_channel(addr)
        stub = info_pb2_grpc.InfoStub(channel)
        resp = stub.All(info_pb2.InfoRequest(selector=""), timeout=timeout_sec)

        # Prefer the *connected* address for host/port. Only override if service advertises a real reachable host.
        resp_hostport = (getattr(resp, "host", "") or "").strip()
        parsed = _try_parse_resp_host(resp_hostport)
        if parsed:
            host, port = parsed

        # Whisper model name is advertised by ytcms in labels["model"]; "version" is the legacy fallback.
        labels = dict(getattr(resp, "labels", {}) or {})
        model = (labels.get("model") or getattr(resp, "version", None) or "").strip()
        diarization = str(labels.get("diarization") or "").strip() == "1"
        dz_models, dz_default = _parse_diarization_models(labels)

        return {
            "host": host,
            "port": port,
            "model": model,
            "app_name": getattr(resp, "app_name", "") or "",
            "instance_id": getattr(resp, "instance_id", "") or "",
            "diarization": diarization,
            # embedding models the server offers for speaker colouring: [{"id","title","default"}], may be empty
            "diarization_models": dz_models,
            "diarization_default_model": dz_default,
        }
    except Exception:
        return {"host": host, "port": port, "model": "", "app_name": "", "instance_id": "", "diarization": False,
                "diarization_models": [], "diarization_default_model": ""}
    finally:
        try:
            if channel is not None:
                channel.close()
        except Exception:
            pass