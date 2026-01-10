from __future__ import annotations
import grpc
from typing import Tuple, List, Dict, Any

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

    # Use plaintext channel for MVP
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

        # Convert google.protobuf.Struct to dict (if present)
        meta: Dict[str, Any] = {}
        try:
            if hasattr(resp, "meta") and resp.meta is not None:
                meta = dict(resp.meta)
        except Exception:
            meta = {}

        return langs, default_src, meta
    finally:
        await channel.close()