import os
import sys
import time
import pathlib
import grpc
from typing import Callable, Dict, List, Optional, Tuple, Any

from config.ytsprites.ytsprites_cfg import (
    ytsprites_servers,
    YTSPRITES_TOKEN,
    YTSPRITES_STATUS_TIMEOUT,
    YTSPRITES_RESULT_TIMEOUT,
    YTSPRITES_DEFAULT_MIME,
    YTSPRITES_SPRITE_STEP_SEC,
    YTSPRITES_SPRITE_COLS,
    YTSPRITES_SPRITE_ROWS,
    YTSPRITES_SPRITE_FORMAT,
    YTSPRITES_SPRITE_QUALITY,
    YTSPRITES_GRPC_MAX_SEND_MB,
    YTSPRITES_GRPC_MAX_RECV_MB,
    YTSPRITES_GRPC_COMPRESSION,
    YTSPRITES_HEALTH_TIMEOUT,
    YTSPRITES_SERVER_TTL,
)

# Import protobuf stubs from ytsprites_proto/
sys.path.append(str(pathlib.Path(__file__).resolve().parent / "ytsprites_proto"))
import ytsprites_pb2 as pb  # type: ignore
import ytsprites_pb2_grpc as pbg  # type: ignore

_last_good: Dict[str, Any] = {"addr": None, "ts": 0.0}


def _auth_metadata() -> List[Tuple[str, str]]:
    md: List[Tuple[str, str]] = []
    tok = (YTSPRITES_TOKEN or "").strip()
    if tok:
        md.append(("authorization", f"Bearer {tok}"))
    return md


def _build_options() -> pb.SpriteOptions:
    return pb.SpriteOptions(
        step_sec=float(YTSPRITES_SPRITE_STEP_SEC),
        cols=int(YTSPRITES_SPRITE_COLS),
        rows=int(YTSPRITES_SPRITE_ROWS),
        format=str(YTSPRITES_SPRITE_FORMAT or "jpg"),
        quality=int(YTSPRITES_SPRITE_QUALITY),
    )


def _channel_for_addr(addr: str) -> grpc.Channel:
    max_send = int(YTSPRITES_GRPC_MAX_SEND_MB) * 1024 * 1024
    max_recv = int(YTSPRITES_GRPC_MAX_RECV_MB) * 1024 * 1024
    compression = None
    if (YTSPRITES_GRPC_COMPRESSION or "").lower() == "gzip":
        compression = grpc.Compression.Gzip

    return grpc.insecure_channel(
        addr,
        options=[
            ("grpc.max_send_message_length", max_send),
            ("grpc.max_receive_message_length", max_recv),
        ],
        compression=compression,
    )


def _open_stub(addr: str) -> pbg.SpritesStub:
    return pbg.SpritesStub(_channel_for_addr(addr))


def health_check(addr: Optional[str] = None) -> bool:
    if not addr:
        cached = _last_good.get("addr")
        if cached:
            addr = str(cached)
        else:
            s0 = ytsprites_servers()[0]
            addr = s0.target

    stub = _open_stub(addr)
    try:
        rep = stub.Health(pb.HealthRequest(), timeout=float(YTSPRITES_HEALTH_TIMEOUT), metadata=_auth_metadata())
        return (rep.status or "").lower() == "ok"
    except Exception:
        return False


def pick_ytsprites_addr() -> str:
    servers = ytsprites_servers()
    if not servers:
        return "127.0.0.1:9094"

    now = time.time()
    cached = _last_good.get("addr")
    ts = float(_last_good.get("ts") or 0.0)
    if cached and (now - ts) < float(YTSPRITES_SERVER_TTL):
        return str(cached)

    for s in servers:
        addr = s.target
        if health_check(addr):
            _last_good["addr"] = addr
            _last_good["ts"] = now
            return addr

    addr0 = servers[0].target
    _last_good["addr"] = addr0
    _last_good["ts"] = now
    return addr0


def create_job_storage_driven(
    *,
    video_id: str,
    source_storage_addr: str,
    source_rel_path: str,
    out_storage_addr: str,
    out_base_rel_dir: str,
    video_mime: Optional[str] = None,
    filename: str = "original.webm",
    storage_token: str = "",
) -> Tuple[str, str]:
    """
    New protocol: CreateJob tells ytsprites where to read source and where to write output.
    Returns (job_id, job_server_addr).
    """
    mime = (video_mime or YTSPRITES_DEFAULT_MIME).strip() or YTSPRITES_DEFAULT_MIME
    addr = pick_ytsprites_addr()
    stub = _open_stub(addr)

    req = pb.CreateJobRequest(
        video_id=video_id,
        filename=filename or "",
        video_mime=mime,
        options=_build_options(),
        source=pb.SourceRef(
            storage=pb.StorageRef(address=str(source_storage_addr or ""), tls=False, token=str(storage_token or "")),
            rel_path=str(source_rel_path or ""),
        ),
        output=pb.OutputRef(
            storage=pb.StorageRef(address=str(out_storage_addr or ""), tls=False, token=str(storage_token or "")),
            base_rel_dir=str(out_base_rel_dir or ""),
            sprites_rel_dir="sprites",
            vtt_name="sprites.vtt",
        ),
    )

    rep = stub.CreateJob(req, timeout=10.0, metadata=_auth_metadata())
    if not rep.accepted or not rep.job_id:
        raise RuntimeError(f"CreateJob rejected for video_id={video_id}: {rep.message}")
    return rep.job_id, addr


def watch_status(
    job_id: str,
    job_server: str,
    on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Optional[pb.StatusUpdate]:
    stub = _open_stub(job_server)
    last = None
    start_ts = time.time()
    try:
        for upd in stub.WatchStatus(
            pb.StatusRequest(job_id=job_id),
            timeout=YTSPRITES_STATUS_TIMEOUT,
            metadata=_auth_metadata(),
        ):
            last = upd
            item = {
                "job_id": upd.job_id,
                "state": upd.state,
                "percent": upd.percent,
                "message": upd.message,
                "bytes_processed": getattr(upd, "bytes_processed", 0),
            }
            if on_update:
                try:
                    on_update(item)
                except Exception:
                    pass
            if upd.state in (pb.JOB_STATE_DONE, pb.JOB_STATE_FAILED, pb.JOB_STATE_CANCELED):
                break
            if (time.time() - start_ts) > YTSPRITES_STATUS_TIMEOUT:
                break
    except grpc.RpcError:
        pass
    return last


def get_result(job_id: str, job_server: str) -> pb.ResultReply:
    stub = _open_stub(job_server)
    rep: pb.ResultReply = stub.GetResult(
        pb.GetResultRequest(job_id=job_id),
        timeout=YTSPRITES_RESULT_TIMEOUT,
        metadata=_auth_metadata(),
    )
    return rep


async def create_thumbnails_job(
    video_id: str,
    src_path: Optional[str],
    out_base_path: str,
    src_url: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Backward-compat shim for legacy call sites.

    IMPORTANT: It no longer uploads/reads src_path. Instead it expects `extra` to include:
      - storage_addr: ytstorage grpc host:port
      - storage_token: (optional)
      - source_rel_path: rel path to original video in storage
      - out_base_rel_dir: base dir where to write sprites/vtt (usually storage_rel)

    Returns the legacy-ish dict:
      { ok, job_id, vtt_rel, sprites }
    where vtt_rel/sprites are RELATIVE to out_base_rel_dir (like before).
    """
    if extra is None:
        raise ValueError("create_thumbnails_job legacy shim requires extra dict with storage params")

    storage_addr = str(extra.get("storage_addr") or "").strip()
    storage_token = str(extra.get("storage_token") or "").strip()
    source_rel_path = str(extra.get("source_rel_path") or "").strip().lstrip("/")
    out_base_rel_dir = str(extra.get("out_base_rel_dir") or "").strip().lstrip("/")

    if not storage_addr or not source_rel_path or not out_base_rel_dir:
        raise ValueError("extra must include storage_addr, source_rel_path, out_base_rel_dir")

    job_id, job_server = await asyncio.to_thread(
        create_job_storage_driven,
        video_id=video_id,
        source_storage_addr=storage_addr,
        source_rel_path=source_rel_path,
        out_storage_addr=storage_addr,
        out_base_rel_dir=out_base_rel_dir,
        video_mime=(extra.get("video_mime") or None),
        filename=str(extra.get("filename") or "original.webm"),
        storage_token=storage_token,
    )

    await asyncio.to_thread(watch_status, job_id, job_server)
    rep = await asyncio.to_thread(get_result, job_id, job_server)

    if rep.state != rep.JOB_STATE_DONE:
        raise RuntimeError(rep.message or "ytsprites failed")

    # Convert absolute rel paths back to "relative to out_base_rel_dir"
    base_prefix = out_base_rel_dir.rstrip("/") + "/"

    vtt_rel = ""
    if rep.vtt and rep.vtt.rel_path:
        vtt_rel = rep.vtt.rel_path
        if vtt_rel.startswith(base_prefix):
            vtt_rel = vtt_rel[len(base_prefix):]

    sprites_rel: List[str] = []
    for art in rep.sprites:
        if not art.rel_path:
            continue
        p = art.rel_path
        if p.startswith(base_prefix):
            p = p[len(base_prefix):]
        sprites_rel.append(p)

    return {"ok": True, "job_id": job_id, "vtt_rel": vtt_rel, "sprites": sprites_rel}