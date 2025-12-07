import os
import sys
import time
import pathlib
import asyncio
import grpc
from typing import Callable, Dict, List, Optional, Tuple, Any

from config.ytsprites.ytsprites_cfg import (
    ytsprites_address,
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
)

# Import protobuf stubs: add the ytsprites_proto directory to sys.path
# TODO: rework gen_proto.sh with sed, remove this construct (see in ytsprites realization)
sys.path.append(str(pathlib.Path(__file__).resolve().parent / "ytsprites_proto"))
import ytsprites_pb2 as pb
import ytsprites_pb2_grpc as pbg


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


def _read_file_bytes(abs_path: str) -> bytes:
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")
    size = os.path.getsize(abs_path)
    if size > YTSPRITES_MAX_UPLOAD_BYTES:
        raise ValueError(f"File size {size} exceeds YTSPRITES_MAX_UPLOAD_BYTES={YTSPRITES_MAX_UPLOAD_BYTES}")
    with open(abs_path, "rb") as f:
        return f.read()


def _open_stub() -> pbg.SpritesStub:
    addr = ytsprites_address()
    max_send = int(YTSPRITES_GRPC_MAX_SEND_MB) * 1024 * 1024
    max_recv = int(YTSPRITES_GRPC_MAX_RECV_MB) * 1024 * 1024
    compression = None
    if (YTSPRITES_GRPC_COMPRESSION or "").lower() == "gzip":
        compression = grpc.Compression.Gzip

    channel = grpc.insecure_channel(
        addr,
        options=[
            ("grpc.max_send_message_length", max_send),
            ("grpc.max_receive_message_length", max_recv),
        ],
        compression=compression,
    )
    return pbg.SpritesStub(channel)


def health_check() -> bool:
    stub = _open_stub()
    try:
        rep = stub.Health(pb.HealthRequest(), timeout=10.0, metadata=_auth_metadata())
        return (rep.status or "").lower() == "ok"
    except Exception:
        return False


# Send only (get job_id), without waiting for the result
def submit_only(video_id: str, video_abs_path: str, video_mime: Optional[str] = None) -> str:
    data = _read_file_bytes(video_abs_path)
    mime = (video_mime or YTSPRITES_DEFAULT_MIME).strip() or YTSPRITES_DEFAULT_MIME
    req = pb.SubmitRequest(
        video_id=video_id,
        video_bytes=data,
        video_mime=mime,
        options=_build_options(),
    )
    stub = _open_stub()
    rep: pb.SubmitReply = stub.Submit(req, timeout=YTSPRITES_SUBMIT_TIMEOUT, metadata=_auth_metadata())
    if not rep.accepted:
        raise RuntimeError(f"Submit rejected for video_id={video_id}")
    return rep.job_id


def watch_status(job_id: str, on_update: Optional[Callable[[Dict], None]] = None) -> Optional[pb.StatusUpdate]:
    stub = _open_stub()
    last = None
    start_ts = time.time()
    try:
        for upd in stub.WatchStatus(pb.StatusRequest(job_id=job_id), timeout=YTSPRITES_STATUS_TIMEOUT, metadata=_auth_metadata()):
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


# Get results by job_id
def get_result(job_id: str) -> Tuple[str, List[Tuple[str, bytes]], str]:
    stub = _open_stub()
    rep: pb.ResultReply = stub.GetResult(pb.GetResultRequest(job_id=job_id), timeout=YTSPRITES_RESULT_TIMEOUT, metadata=_auth_metadata())
    video_id = rep.video_id
    sprites: List[Tuple[str, bytes]] = []
    for sb in rep.sprites:
        sprites.append((sb.name, bytes(sb.data)))
    vtt = rep.vtt or ""
    return video_id, sprites, vtt


# Send a video file, wait for completion (via status stream) and collect the result
def submit_and_wait(video_id: str, video_abs_path: str, video_mime: Optional[str] = None,
                    on_status: Optional[Callable[[Dict], None]] = None) -> Tuple[str, List[Tuple[str, bytes]], str]:
    job_id = submit_only(video_id, video_abs_path, video_mime=video_mime)
    watch_status(job_id, on_update=on_status)
    return get_result(job_id)


# Local processing via ytsprites
async def create_thumbnails_job(
    video_id: str,
    src_path: Optional[str],
    out_base_path: str,
    src_url: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Thumbs generator. 
    Calls gRPC ytsprites
    Sync processing, saves files to out_base_path.

    Returns:
    {
      "ok": True,
      "job_id": "ytsprites-local",
      "vtt_rel": "sprites.vtt",
      "sprites": ["sprites/sprite_0001.jpg", ..]
    }
    """
    if not src_path and not src_url:
        raise ValueError("src_path or src_url required")
    # Currently only src_path (local file)
    if not src_path or not os.path.isfile(src_path):
        raise FileNotFoundError(f"Video src_path not found: {src_path}")

    mime = (YTSPRITES_DEFAULT_MIME or "video/webm").strip() or "video/webm"

    # Send and wait in sep thread
    video_id2, sprites, vtt_text = await asyncio.to_thread(submit_and_wait, video_id, src_path, mime)

    # Save result close to out_base_path
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