import os
import sys
import time
import pathlib
import asyncio
import grpc
from typing import Callable, Dict, List, Optional, Tuple, Any

from config.ytsprites.ytsprites_cfg import (
    ytsprites_servers,
    YTSPRITES_TOKEN,
    YTSPRITES_SUBMIT_TIMEOUT,
    YTSPRITES_STATUS_TIMEOUT,
    YTSPRITES_RESULT_TIMEOUT,
    YTSPRITES_MAX_UPLOAD_BYTES,
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

# Import protobuf stubs: add the ytsprites_proto directory to sys.path
# TODO: rework gen_proto.sh with sed, remove this construct (see in ytsprites realization)
sys.path.append(str(pathlib.Path(__file__).resolve().parent / "ytsprites_proto"))
import ytsprites_pb2 as pb
import ytsprites_pb2_grpc as pbg


_last_good: Dict[str, Any] = {"addr": None, "ts": 0.0}


def _auth_metadata() -> List[Tuple[str, str]]:
    md: List[Tuple[str, str]] = []
    tok = (YTSPRITES_TOKEN or "").strip()
    if tok:
        md.append(("authorization", f"Bearer {tok}"))
    return md


def _build_options() -> pb.SpriteOptions:
    return pb.SpriteOptions(
        step_sec=YTSPRITES_SPRITE_STEP_SEC,
        cols=YTSPRITES_SPRITE_COLS,
        rows=YTSPRITES_SPRITE_ROWS,
        format=YTSPRITES_SPRITE_FORMAT,
        quality=YTSPRITES_SPRITE_QUALITY,
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
    channel = _channel_for_addr(addr)
    return pbg.SpritesStub(channel)


def health_check(addr: Optional[str] = None) -> bool:
    """
    Service-native healthcheck (Sprites/Health).
    """
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
    """
    Pick first healthy server from YTSPRITES_SERVERS (preferred order).
    TTL-cached.
    """
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


def create_job_only(
    video_id: str,
    *,
    filename: str = "original.webm",
    video_mime: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Returns (job_id, job_server_addr).
    """
    mime = (video_mime or YTSPRITES_DEFAULT_MIME).strip() or YTSPRITES_DEFAULT_MIME
    addr = pick_ytsprites_addr()
    stub = _open_stub(addr)

    req = pb.CreateJobRequest(
        video_id=video_id,
        filename=(filename or ""),
        video_mime=mime,
        options=_build_options(),
    )
    rep: pb.CreateJobReply = stub.CreateJob(req, timeout=YTSPRITES_SUBMIT_TIMEOUT, metadata=_auth_metadata())
    if not rep.accepted or not rep.job_id:
        raise RuntimeError(f"CreateJob rejected for video_id={video_id}: {(rep.message or '')}")
    return rep.job_id, addr


def upload_source(
    job_id: str,
    job_server: str,
    video_abs_path: str,
    *,
    chunk_bytes: int = 4 * 1024 * 1024,
) -> pb.UploadReply:
    """
    Client-streaming upload to the SAME server (affinity).

    Guarantees:
      - offset starts at 0 and strictly increases by len(data)
      - always attempts to send the final chunk with last=True (offset=total_bytes, data=b"")
      - logs bytes_sent and whether last=True was sent
      - on failure: raises; best-effort cancel is attempted if Cancel RPC exists
    """
    if not os.path.isfile(video_abs_path):
        raise FileNotFoundError(f"File not found: {video_abs_path}")

    file_size = os.path.getsize(video_abs_path)

    # Client-side precheck (server may still reject with its own limit)
    if file_size > int(YTSPRITES_MAX_UPLOAD_BYTES):
        raise ValueError(f"File size {file_size} exceeds YTSPRITES_MAX_UPLOAD_BYTES={YTSPRITES_MAX_UPLOAD_BYTES}")

    stub = _open_stub(job_server)

    bytes_sent = 0
    sent_last = False
    started_ts = time.time()
    last_log_ts = started_ts

    print(f"[YTSPRITES][UPLOAD] start job_id={job_id} size={file_size} chunk_bytes={chunk_bytes} server={job_server}")

    def gen():
        nonlocal bytes_sent, sent_last, last_log_ts

        offset = 0
        with open(video_abs_path, "rb") as f:
            while True:
                data = f.read(chunk_bytes)
                if not data:
                    break

                ln = len(data)
                yield pb.UploadChunk(job_id=job_id, offset=offset, data=data, last=False)
                offset += ln
                bytes_sent += ln

                # periodic log (every ~5s)
                now = time.time()
                if (now - last_log_ts) >= 5.0:
                    pct = int((bytes_sent * 100) / file_size) if file_size > 0 else 0
                    print(f"[YTSPRITES][UPLOAD] progress job_id={job_id} bytes_sent={bytes_sent}/{file_size} ({pct}%)")
                    last_log_ts = now

        # REQUIRED final chunk
        yield pb.UploadChunk(job_id=job_id, offset=offset, data=b"", last=True)
        sent_last = True
        print(f"[YTSPRITES][UPLOAD] sent last=true job_id={job_id} final_offset={offset} bytes_sent={bytes_sent}")

    try:
        rep: pb.UploadReply = stub.UploadSource(gen(), timeout=YTSPRITES_SUBMIT_TIMEOUT, metadata=_auth_metadata())

        if not getattr(rep, "accepted", False):
            msg = getattr(rep, "message", "") or ""
            raise RuntimeError(f"UploadSource rejected job_id={job_id}: {msg}")

        elapsed = time.time() - started_ts
        print(
            f"[YTSPRITES][UPLOAD] done job_id={job_id} bytes_sent={bytes_sent} "
            f"sent_last={sent_last} elapsed_sec={elapsed:.2f}"
        )
        return rep

    except grpc.RpcError as e:
        code = getattr(e, "code", lambda: None)()
        details = getattr(e, "details", lambda: "")() or ""

        # Recognize size-limit errors
        if code == grpc.StatusCode.RESOURCE_EXHAUSTED or "Upload too large" in details:
            print(
                f"[YTSPRITES][UPLOAD][ERROR] too_large job_id={job_id} bytes_sent={bytes_sent}/{file_size} "
                f"sent_last={sent_last} code={code} details={details!r}"
            )
            raise RuntimeError("upload_too_large") from e

        print(
            f"[YTSPRITES][UPLOAD][ERROR] grpc_error job_id={job_id} bytes_sent={bytes_sent}/{file_size} "
            f"sent_last={sent_last} code={code} details={details!r}"
        )

        # Best-effort cancel to avoid dangling jobs
        try:
            stub.Cancel(pb.CancelRequest(job_id=job_id), timeout=5.0, metadata=_auth_metadata())
        except Exception:
            pass

        raise

    except Exception as e:
        print(
            f"[YTSPRITES][UPLOAD][ERROR] exception job_id={job_id} bytes_sent={bytes_sent}/{file_size} "
            f"sent_last={sent_last} exc={e!r}"
        )
        # Best-effort cancel to avoid dangling jobs
        try:
            stub.Cancel(pb.CancelRequest(job_id=job_id), timeout=5.0, metadata=_auth_metadata())
        except Exception:
            pass
        raise


def submit_only(video_id: str, video_abs_path: str, video_mime: Optional[str] = None) -> Tuple[str, str]:
    """
    Returns (job_id, job_server_addr).
    """
    job_id, addr = create_job_only(
        video_id,
        filename=os.path.basename(video_abs_path) or "original.webm",
        video_mime=video_mime,
    )
    upload_source(job_id, addr, video_abs_path)
    return job_id, addr


def watch_status(job_id: str, job_server: str, on_update: Optional[Callable[[Dict], None]] = None) -> Optional[pb.StatusUpdate]:
    """
    IMPORTANT: affinity — status is watched on the SAME server where job was created.
    """
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


def get_result(job_id: str, job_server: str) -> Tuple[str, List[Tuple[str, bytes]], str]:
    """
    IMPORTANT: affinity — result is fetched from the SAME server where job was created.
    """
    stub = _open_stub(job_server)
    rep: pb.ResultReply = stub.GetResult(
        pb.GetResultRequest(job_id=job_id),
        timeout=YTSPRITES_RESULT_TIMEOUT,
        metadata=_auth_metadata(),
    )
    video_id = rep.video_id
    sprites: List[Tuple[str, bytes]] = []
    for sb in rep.sprites:
        sprites.append((sb.name, bytes(sb.data)))
    vtt = rep.vtt or ""
    return video_id, sprites, vtt


def submit_and_wait(
    video_id: str,
    video_abs_path: str,
    video_mime: Optional[str] = None,
    on_status: Optional[Callable[[Dict], None]] = None,
) -> Tuple[str, List[Tuple[str, bytes]], str]:
    """
    Full flow with affinity:
      - CreateJob chooses job_server
      - UploadSource sends chunks to the SAME job_server
      - WatchStatus + GetResult use the SAME job_server
    """
    job_id, job_server = submit_only(video_id, video_abs_path, video_mime=video_mime)
    watch_status(job_id, job_server, on_update=on_status)
    return get_result(job_id, job_server)


async def create_thumbnails_job(
    video_id: str,
    src_path: Optional[str],
    out_base_path: str,
    src_url: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Thumbs generator.
    Calls gRPC ytsprites.
    Sync processing, saves files to out_base_path.

    Returns:
    {
      "ok": True,
      "job_id": "...",
      "vtt_rel": "sprites.vtt",
      "sprites": ["sprites/sprite_0001.jpg", ..]
    }
    """
    if not src_path and not src_url:
        raise ValueError("src_path or src_url required")
    if not src_path or not os.path.isfile(src_path):
        raise FileNotFoundError(f"Video src_path not found: {src_path}")

    mime = (YTSPRITES_DEFAULT_MIME or "video/webm").strip() or "video/webm"

    # Run gRPC sync client in a separate thread (keeps event loop responsive).
    video_id2, sprites, vtt_text = await asyncio.to_thread(submit_and_wait, video_id, src_path, mime)

    os.makedirs(out_base_path, exist_ok=True)

    # VTT
    vtt_abs = os.path.join(out_base_path, "sprites.vtt")
    try:
        with open(vtt_abs, "w", encoding="utf-8") as f:
            f.write(vtt_text or "")
    except Exception:
        try:
            with open(vtt_abs, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass

    # sprites/ subfolder
    sprites_dir_abs = os.path.join(out_base_path, "sprites")
    try:
        os.makedirs(sprites_dir_abs, exist_ok=True)
    except Exception:
        pass

    rel_sprites: List[str] = []
    for name, data in sprites:
        rel_path = os.path.join("sprites", name)
        abs_path = os.path.join(out_base_path, rel_path)
        try:
            with open(abs_path, "wb") as f:
                f.write(data or b"")
            rel_sprites.append(rel_path)
        except Exception:
            continue

    return {
        "ok": True,
        "job_id": "ytsprites-local",
        "vtt_rel": "sprites.vtt",
        "sprites": rel_sprites,
    }