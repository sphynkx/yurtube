# Client part to operation with external ytsprites service (replacement for ytms)

import os
import sys
import pathlib
import time
import grpc
from typing import Callable, Dict, List, Optional, Tuple

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
)

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
    channel = grpc.insecure_channel(addr)
    return pbg.SpritesStub(channel)

def health_check() -> bool:
    stub = _open_stub()
    try:
        rep = stub.Health(pb.HealthRequest(), timeout=10.0, metadata=_auth_metadata())
        return (rep.status or "").lower() == "ok"
    except Exception:
        return False


# Send only (get job_id), dont wait for result
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