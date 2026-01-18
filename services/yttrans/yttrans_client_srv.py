from __future__ import annotations

import os
import time
import grpc
from typing import Tuple, List, Dict, Any, Optional

from config.yttrans.yttrans_cfg import load_yttrans_config, YTTransServer
from grpc_health.v1 import health_pb2, health_pb2_grpc  # type: ignore

try:
    from services.yttrans.yttrans_proto import yttrans_pb2, yttrans_pb2_grpc  # type: ignore
except Exception:
    yttrans_pb2 = None
    yttrans_pb2_grpc = None


_YTTRANS_HEALTH_TIMEOUT_SEC = float((os.getenv("YTTRANS_HEALTH_TIMEOUT", "") or "0.7").strip() or "0.7")
_YTTRANS_SERVER_TTL_SEC = float((os.getenv("YTTRANS_SERVER_TTL", "") or "10").strip() or "10")

_last_good: Dict[str, Any] = {"server": None, "ts": 0.0}


def _auth_md(token: Optional[str]) -> List[Tuple[str, str]]:
    md: List[Tuple[str, str]] = []
    tok = (token or "").strip()
    if tok:
        md.append(("authorization", f"Bearer {tok}"))
    return md


def _normalize_target(s: str) -> str:
    return (s or "").strip()


def _parse_target_to_server(target: str) -> YTTransServer:
    """
    Convert 'host:port' (stored in meta as job_server) back into YTTransServer.
    Token is resolved from current config list (if any).
    """
    t = _normalize_target(target)
    cfg = load_yttrans_config()

    # Try exact match by target
    for s in (cfg.servers or []):
        if _normalize_target(getattr(s, "target", "")) == t:
            return s

    # Fallback: parse host/port, no token
    host = cfg.host
    port = cfg.port
    if t.startswith("["):
        rb = t.find("]")
        if rb > 0:
            host = t[1:rb]
            rest = t[rb + 1 :]
            if rest.startswith(":"):
                try:
                    port = int(rest[1:])
                except Exception:
                    port = cfg.port
            return YTTransServer(host=host, port=port, token=None)

    if ":" in t:
        h, p = t.rsplit(":", 1)
        host = h.strip() or host
        try:
            port = int(p.strip())
        except Exception:
            port = port
    return YTTransServer(host=host, port=port, token=None)


async def _healthcheck_server(server: YTTransServer) -> bool:
    channel = grpc.aio.insecure_channel(server.target)
    try:
        stub = health_pb2_grpc.HealthStub(channel)

        # 1) service-specific
        try:
            resp = await stub.Check(
                health_pb2.HealthCheckRequest(service="yttrans.v1.Translator"),
                timeout=_YTTRANS_HEALTH_TIMEOUT_SEC,
            )
            if resp.status == health_pb2.HealthCheckResponse.SERVING:
                return True
        except grpc.aio.AioRpcError:
            pass
        except Exception:
            pass

        # 2) global
        try:
            resp2 = await stub.Check(
                health_pb2.HealthCheckRequest(service=""),
                timeout=_YTTRANS_HEALTH_TIMEOUT_SEC,
            )
            return resp2.status == health_pb2.HealthCheckResponse.SERVING
        except Exception:
            return False
    except Exception:
        return False
    finally:
        await channel.close()


async def pick_yttrans_server() -> YTTransServer:
    cfg = load_yttrans_config()

    servers = list(cfg.servers or [])
    if not servers:
        servers = [YTTransServer(host=cfg.host, port=cfg.port, token=cfg.token)]

    now = time.time()
    cached = _last_good.get("server")
    ts = float(_last_good.get("ts") or 0.0)

    if cached and (now - ts) < _YTTRANS_SERVER_TTL_SEC:
        return cached

    for s in servers:
        ok = await _healthcheck_server(s)
        if ok:
            _last_good["server"] = s
            _last_good["ts"] = now
            return s

    _last_good["server"] = servers[0]
    _last_good["ts"] = now
    return servers[0]


async def list_languages() -> Tuple[List[str], str, Dict[str, Any]]:
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError(
            "yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto"
        )

    server = await pick_yttrans_server()
    channel = grpc.aio.insecure_channel(server.target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.ListLanguagesRequest()  # type: ignore
        resp = await stub.ListLanguages(req, metadata=_auth_md(server.token))  # type: ignore

        langs = list(resp.target_langs or [])
        default_src = resp.default_source_lang or "auto"

        meta: Dict[str, Any] = {}
        try:
            if hasattr(resp, "meta") and resp.meta is not None:
                meta = dict(resp.meta)
        except Exception:
            meta = {}

        return langs, default_src, meta
    finally:
        await channel.close()


async def submit_translate(
    video_id: str,
    src_vtt: str,
    src_lang: str,
    target_langs: List[str],
    options: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Submit translation job and return (job_id, job_server_target).
    job_server_target is 'host:port' (same format as grpc channel target).
    """
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError(
            "yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto"
        )

    server = await pick_yttrans_server()
    channel = grpc.aio.insecure_channel(server.target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.SubmitTranslateRequest(  # type: ignore
            video_id=video_id,
            src_vtt=src_vtt or "",
            src_lang=src_lang or "auto",
            target_langs=list(target_langs or []),
        )
        if options:
            from google.protobuf.struct_pb2 import Struct  # type: ignore

            s = Struct()
            s.update(options)
            req.options.CopyFrom(s)  # type: ignore

        ack = await stub.SubmitTranslate(req, metadata=_auth_md(server.token))  # type: ignore
        if not ack.accepted:
            raise RuntimeError(f"job_rejected: {ack.message or ''}")
        return (ack.job_id or "", server.target)
    finally:
        await channel.close()


async def get_status(job_id: str, server: Optional[str] = None) -> Dict[str, Any]:
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError(
            "yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto"
        )

    s = _parse_target_to_server(server) if server else await pick_yttrans_server()
    channel = grpc.aio.insecure_channel(s.target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.GetStatusRequest(job_id=job_id)  # type: ignore
        resp = await stub.GetStatus(req, metadata=_auth_md(s.token))  # type: ignore

        state_map = {0: "idle", 1: "queued", 2: "running", 3: "done", 4: "failed"}
        state = state_map.get(getattr(resp, "state", 0), "idle")
        percent = int(getattr(resp, "percent", -1))
        message = getattr(resp, "message", "")
        video_id = getattr(resp, "video_id", "")

        meta: Dict[str, Any] = {}
        try:
            if hasattr(resp, "meta") and resp.meta is not None:
                meta = dict(resp.meta)
        except Exception:
            meta = {}

        return {"state": state, "percent": percent, "message": message, "video_id": video_id, "meta": meta}
    finally:
        await channel.close()


async def get_partial_result(job_id: str, server: Optional[str] = None) -> Dict[str, Any]:
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError(
            "yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto"
        )

    s = _parse_target_to_server(server) if server else await pick_yttrans_server()
    channel = grpc.aio.insecure_channel(s.target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.GetPartialResultRequest(job_id=job_id)  # type: ignore
        resp = await stub.GetPartialResult(req, metadata=_auth_md(s.token))  # type: ignore

        state_map = {0: "idle", 1: "queued", 2: "running", 3: "done", 4: "failed"}
        state = state_map.get(getattr(resp, "state", 0), "idle")
        percent = int(getattr(resp, "percent", -1))
        message = getattr(resp, "message", "")
        video_id = getattr(resp, "video_id", "")

        ready_langs = list(getattr(resp, "ready_langs", []) or [])
        total_langs = int(getattr(resp, "total_langs", 0) or 0)

        meta: Dict[str, Any] = {}
        try:
            if hasattr(resp, "meta") and resp.meta is not None:
                meta = dict(resp.meta)
        except Exception:
            meta = {}

        return {
            "job_id": getattr(resp, "job_id", "") or job_id,
            "video_id": video_id,
            "state": state,
            "percent": percent,
            "message": message,
            "ready_langs": ready_langs,
            "total_langs": total_langs,
            "meta": meta,
        }
    finally:
        await channel.close()


async def get_result(job_id: str, server: Optional[str] = None) -> Tuple[str, str, List[Tuple[str, str]], Dict[str, Any]]:
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError(
            "yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto"
        )

    s = _parse_target_to_server(server) if server else await pick_yttrans_server()
    channel = grpc.aio.insecure_channel(s.target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.GetResultRequest(job_id=job_id)  # type: ignore
        resp = await stub.GetResult(req, metadata=_auth_md(s.token))  # type: ignore

        video_id = getattr(resp, "video_id", "")
        default_lang = getattr(resp, "default_lang", "") or "auto"

        entries: List[Tuple[str, str]] = []
        for e in list(getattr(resp, "entries", [])):
            lang = getattr(e, "lang", "")
            vtt = getattr(e, "vtt", "") or ""
            if lang:
                entries.append((lang, vtt))

        meta: Dict[str, Any] = {}
        try:
            if hasattr(resp, "meta") and resp.meta is not None:
                meta = dict(resp.meta)
        except Exception:
            meta = {}

        return video_id, default_lang, entries, meta
    finally:
        await channel.close()