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
    """
    Stream file to the service using the original chunk contract:
    each chunk includes request_id, video_id, lang, task, filename, data and 'last' flag.
    """
    request_id = uuid.uuid4().hex
    filename = os.path.basename(video_path)

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
                filename=filename,
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

    Service now uses async contract: Submit returns job_id + status (QUEUED/PROCESSING),
    and the result is fetched separately via GetResult(job_id).
    """
    addr = ytcms_address()
    lang = (lang or YTCMS_DEFAULT_LANG).strip() or "auto"
    task = (task or YTCMS_DEFAULT_TASK).strip() or "transcribe"

    print(f"[YTCMS] submit start video_id={video_id} path={video_path} lang={lang} task={task}")

    channel = grpc.insecure_channel(addr)
    stub = captions_pb2_grpc.CaptionsServiceStub(channel)
    md = [("authorization", f"Bearer {YTCMS_TOKEN}")]

    # Submit job (each RPC has a deadline)
    submit_reply = stub.Submit(
        _upload_stream(video_path, video_id, lang, task),
        metadata=md,
        timeout=submit_timeout,
    )

    submit_status = (submit_reply.status or "").strip().lower()
    job_id = submit_reply.job_id or ""
    print(f"[YTCMS] submit reply video_id={video_id} job_id={job_id} status={submit_status} err={(submit_reply.error or '')}")

    if submit_status not in ("queued", "processing"):
        # In async mode, SubmitReply.content is empty; rely on .error if any
        raise RuntimeError(f"Submit failed: {getattr(submit_reply, 'error', '')}")

    # Poll status
    last_status = None
    final_status = None
    final_error = ""
    while True:
        st = stub.GetStatus(
            captions_pb2.JobStatusRequest(job_id=job_id),
            metadata=md,
            timeout=status_timeout,
        )
        st_status = (st.status or "").strip().lower()
        if st_status != last_status:
            print(f"[YTCMS] status video_id={video_id} job_id={job_id} status={st_status} err={(st.error or '')}")
            last_status = st_status

        if st_status in ("done", "error", "not_found"):
            final_status = st_status
            final_error = getattr(st, "error", "") or ""
            break

        time.sleep(poll_interval)

    if final_status == "error":
        print(f"[YTCMS] job failed video_id={video_id} job_id={job_id} err={final_error}")
        raise RuntimeError(f"Job failed: {final_error}")
    if final_status == "not_found":
        print(f"[YTCMS] job not found video_id={video_id} job_id={job_id}")
        raise RuntimeError("Job not found")

    print(f"[YTCMS] job done video_id={video_id} job_id={job_id} -> fetching result")

    # Fetch result
    res = stub.GetResult(
        captions_pb2.ResultRequest(job_id=job_id),
        metadata=md,
        timeout=result_timeout,
    )

    # Small summary for diagnostics
    vtt_len = len(getattr(res, "vtt", "") or getattr(res, "content", "") or "")
    meta_lang = getattr(res, "detected_lang", None)
    print(f"[YTCMS] result received video_id={video_id} job_id={job_id} vtt_len={vtt_len} detected_lang={meta_lang}")

    return res