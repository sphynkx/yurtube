import os
import time
import uuid
import grpc
import sys
import pathlib
from typing import Iterator, Optional

from config.ytcms_cfg import ytcms_address, YTCMS_TOKEN, YTCMS_DEFAULT_LANG, YTCMS_DEFAULT_TASK

# Make generated stubs importable as top-level modules (captions_pb2_grpc imports captions_pb2).
sys.path.append(str(pathlib.Path(__file__).resolve().parent / "ytcms_proto"))

import captions_pb2  # noqa: E402
import captions_pb2_grpc  # noqa: E402


def _upload_stream(video_path: str, video_id: str, lang: str, task: str) -> Iterator[captions_pb2.UploadChunk]:
    # Client-side request id for correlation
    request_id = uuid.uuid4().hex

    # Stream file chunks (avoid loading entire file into memory)
    with open(video_path, "rb") as f:
        while True:
            chunk = f.read(2_000_000)
            if not chunk:
                break
            # Determine 'last' by peeking next byte
            pos = f.tell()
            nxt = f.read(1)
            is_last = not nxt
            if nxt:
                f.seek(pos)
            yield captions_pb2.UploadChunk(
                request_id=request_id,
                video_id=video_id,
                lang=lang,
                task=task,
                data=chunk,
                last=is_last,
                filename=os.path.basename(video_path),
            )


def submit_and_wait(
    video_path: str,
    video_id: str,
    lang: Optional[str] = None,
    task: Optional[str] = None,
    poll_interval: float = 1.5,
    submit_timeout: float = 1800.0,
    status_timeout: float = 5.0,
    result_timeout: float = 30.0,
) -> captions_pb2.ResultReply:
    """
    Submit a video to ytcms for transcription, poll status, and fetch final result.
    Deadlines (timeouts) are set to fail fast if service is unreachable.
    """
    addr = ytcms_address()
    lang = (lang or YTCMS_DEFAULT_LANG).strip() or "auto"
    task = (task or YTCMS_DEFAULT_TASK).strip() or "transcribe"

    channel = grpc.insecure_channel(addr)
    stub = captions_pb2_grpc.CaptionsServiceStub(channel)
    md = [("authorization", f"Bearer {YTCMS_TOKEN}")]

    # Submit job (deadline)
    submit_reply = stub.Submit(_upload_stream(video_path, video_id, lang, task), metadata=md, timeout=submit_timeout)
    if submit_reply.status != "queued":
        raise RuntimeError(f"Submit failed: {submit_reply.error}")

    job_id = submit_reply.job_id

    # Poll status (each call with its own deadline)
    while True:
        st = stub.GetStatus(captions_pb2.JobStatusRequest(job_id=job_id), metadata=md, timeout=status_timeout)
        if st.status in ("done", "error"):
            break
        time.sleep(poll_interval)

    if st.status == "error":
        raise RuntimeError(f"Job failed: {st.error}")

    # Fetch final result (deadline)
    result = stub.GetResult(captions_pb2.ResultRequest(job_id=job_id), metadata=md, timeout=result_timeout)
    return result