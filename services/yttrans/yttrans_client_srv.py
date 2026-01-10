from __future__ import annotations
import grpc
import asyncio
from typing import Tuple, List, Dict, Any, Optional

from config.yttrans.yttrans_cfg import load_yttrans_config

try:
    from services.yttrans.yttrans_proto import yttrans_pb2, yttrans_pb2_grpc  # type: ignore
except Exception as e:
    yttrans_pb2 = None
    yttrans_pb2_grpc = None


async def list_languages() -> Tuple[List[str], str, Dict[str, Any]]:
    """
    Calls yttrans.v1.Translator/ListLanguages and returns:
    (target_langs, default_source_lang, meta)
    """
    cfg = load_yttrans_config()
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError("yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto")

    target = f"{cfg.host}:{cfg.port}"
    channel = grpc.aio.insecure_channel(target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.ListLanguagesRequest()  # type: ignore
        md = []
        if cfg.token:
            md.append(("authorization", f"Bearer {cfg.token}"))
        resp = await stub.ListLanguages(req, metadata=md)  # type: ignore

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


async def submit_translate(video_id: str, src_vtt: str, src_lang: str, target_langs: List[str], options: Optional[Dict[str, Any]] = None) -> str:
    """
    Submit translation job and return job_id.
    """
    cfg = load_yttrans_config()
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError("yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto")

    target = f"{cfg.host}:{cfg.port}"
    channel = grpc.aio.insecure_channel(target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.SubmitTranslateRequest(  # type: ignore
            video_id=video_id,
            src_vtt=src_vtt or "",
            src_lang=src_lang or "auto",
            target_langs=list(target_langs or []),
        )
        # options via Struct (optional)
        if options:
            from google.protobuf.struct_pb2 import Struct  # type: ignore
            s = Struct()
            s.update(options)
            req.options.CopyFrom(s)  # type: ignore

        md = []
        if cfg.token:
            md.append(("authorization", f"Bearer {cfg.token}"))
        ack = await stub.SubmitTranslate(req, metadata=md)  # type: ignore
        if not ack.accepted:
            raise RuntimeError(f"job_rejected: {ack.message or ''}")
        return ack.job_id or ""
    finally:
        await channel.close()


async def get_status(job_id: str) -> Dict[str, Any]:
    """
    Get job status: returns dict {state, percent, message, video_id, meta}
    """
    cfg = load_yttrans_config()
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError("yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto")

    target = f"{cfg.host}:{cfg.port}"
    channel = grpc.aio.insecure_channel(target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.GetStatusRequest(job_id=job_id)  # type: ignore
        md = []
        if cfg.token:
            md.append(("authorization", f"Bearer {cfg.token}"))
        resp = await stub.GetStatus(req, metadata=md)  # type: ignore

        # resp.state is enum; map to string
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


async def get_result(job_id: str) -> Tuple[str, str, List[Tuple[str, str]], Dict[str, Any]]:
    """
    Get job result:
    Returns (video_id, default_lang, entries[(lang, vtt)], meta)
    """
    cfg = load_yttrans_config()
    if yttrans_pb2 is None or yttrans_pb2_grpc is None:
        raise RuntimeError("yttrans protobuf stubs not found. Generate stubs from services/yttrans/yttrans_proto/yttrans.proto")

    target = f"{cfg.host}:{cfg.port}"
    channel = grpc.aio.insecure_channel(target)
    try:
        stub = yttrans_pb2_grpc.TranslatorStub(channel)  # type: ignore
        req = yttrans_pb2.GetResultRequest(job_id=job_id)  # type: ignore
        md = []
        if cfg.token:
            md.append(("authorization", f"Bearer {cfg.token}"))
        resp = await stub.GetResult(req, metadata=md)  # type: ignore

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