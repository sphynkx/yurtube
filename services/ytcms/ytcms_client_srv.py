## SRTG_2MODIFY: os.path.
## SRTG_2MODIFY: open(
## SRTG_2MODIFY: pathlib
## SRTG_2MODIFY: _path
import os
import time
import uuid
import grpc
import sys
import pathlib
from typing import Iterator, Optional, Tuple, Callable

from config.ytcms_cfg import (
    ytcms_address, 
    YTCMS_TOKEN, 
    YTCMS_DEFAULT_LANG, 
    YTCMS_DEFAULT_TASK,
    YTCMS_POLL_INTERVAL,
    YTCMS_SUBMIT_TIMEOUT,
    YTCMS_STATUS_TIMEOUT,
    YTCMS_RESULT_TIMEOUT,
    )

# Make generated stubs importable as top-level modules (captions_pb2_grpc imports captions_pb2).
sys.path.append(str(pathlib.Path(__file__).resolve().parent / "ytcms_proto"))

import captions_pb2
import captions_pb2_grpc


def _upload_stream(video_path: str, video_id: str, lang: str, task: str) -> Iterator[captions_pb2.UploadChunk]:
    """
    Streaming a file to a service: original contract with chunks.
    Each chunk includes: request_id, video_id, lang, task, filename, data, last.
    """
    request_id = uuid.uuid4().hex
    filename = os.path.basename(video_path)

    with open(video_path, "rb") as f:
        while True:
            chunk = f.read(2_000_000)
            if not chunk:
                break
            # define 'last' - see the byte ahead
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


def _extract_percent(status_reply: captions_pb2.JobStatusReply) -> Tuple[int, float]:
    """
    Safely extracts the percentage from JobStatusReply.
    Returns (percent_int_0_100_or_-1, progress_0_1_or_-1.0)
    """
    p_int = -1
    p_norm = -1.0
    try:
        # percent: 0..100 (int)
        if hasattr(status_reply, "percent"):
            val = int(status_reply.percent)
            if 0 <= val <= 100:
                p_int = val
        # progress: 0..1 (float)
        if hasattr(status_reply, "progress"):
            valf = float(status_reply.progress)
            if 0.0 <= valf <= 1.0:
                p_norm = valf
                # if percent undef -use progress
                if p_int < 0:
                    p_int = max(0, min(100, int(round(valf * 100))))
    except Exception:
        pass
    return p_int, p_norm


def submit_and_wait(
    video_path: str,
    video_id: str,
    lang: Optional[str] = None,
    task: Optional[str] = None,
    poll_interval: float = YTCMS_POLL_INTERVAL,
    submit_timeout: float = YTCMS_SUBMIT_TIMEOUT,
    status_timeout: float = YTCMS_STATUS_TIMEOUT,
    result_timeout: float = YTCMS_RESULT_TIMEOUT,
    on_status: Optional[Callable[[str, str, str, int, float], None]] = None,
) -> captions_pb2.ResultReply:
    """
    Submit a video to ytcms (asynchronous contract), poll the status, and get the result.
    Submit returns job_id + status (queued/processing), then poll GetStatus,
    and upon completion, retrieve the result via GetResult(job_id).

    on_status(video_id, job_id, status, percent, progress):
    - callback is called on every status/progress change.
    """
    addr = ytcms_address()
    lang = (lang or YTCMS_DEFAULT_LANG).strip() or "auto"
    task = (task or YTCMS_DEFAULT_TASK).strip() or "transcribe"

    print(f"[YTCMS] submit start video_id={video_id} path={video_path} lang={lang} task={task}")

    channel = grpc.insecure_channel(addr)
    stub = captions_pb2_grpc.CaptionsServiceStub(channel)
    md = [("authorization", f"Bearer {YTCMS_TOKEN}")]

    # Submit
    submit_reply = stub.Submit(
        _upload_stream(video_path, video_id, lang, task),
        metadata=md,
        timeout=submit_timeout,
    )

    submit_status = (submit_reply.status or "").strip().lower()
    job_id = submit_reply.job_id or ""
    print(f"[YTCMS] submit reply video_id={video_id} job_id={job_id} status={submit_status} err={(submit_reply.error or '')}")

    if submit_status not in ("queued", "processing"):
        raise RuntimeError(f"Submit failed: {getattr(submit_reply, 'error', '')}")

    # callback init
    try:
        if on_status:
            on_status(video_id, job_id, submit_status, -1, -1.0)
    except Exception:
        pass

    # Call status
    last_status = None
    final_status = None
    final_error = ""
    last_percent = -1
    last_progress = -1.0

    while True:
        st = stub.GetStatus(
            captions_pb2.JobStatusRequest(job_id=job_id),
            metadata=md,
            timeout=status_timeout,
        )
        st_status = (st.status or "").strip().lower()
        # get %%
        p_int, p_norm = _extract_percent(st)

        # callback on every tick
        try:
            if on_status:
                on_status(video_id, job_id, st_status, p_int, p_norm)
        except Exception:
            pass

        if st_status != last_status:
            if p_int >= 0:
                print(f"[YTCMS] status video_id={video_id} job_id={job_id} status={st_status} percent={p_int} err={(st.error or '')}")
            elif p_norm >= 0.0:
                print(f"[YTCMS] status video_id={video_id} job_id={job_id} status={st_status} progress={p_norm:.3f} err={(st.error or '')}")
            else:
                print(f"[YTCMS] status video_id={video_id} job_id={job_id} status={st_status} err={(st.error or '')}")
            last_status = st_status

        # update last %%-s
        if p_int >= 0:
            last_percent = p_int
        if p_norm >= 0.0:
            last_progress = p_norm

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

    # Get result from YTCMS
    res = stub.GetResult(
        captions_pb2.ResultRequest(job_id=job_id),
        metadata=md,
        timeout=result_timeout,
    )

    # Add percent/progress to metadata
    try:
        if not hasattr(res, "percent"):
            setattr(res, "percent", last_percent)
        if not hasattr(res, "progress"):
            setattr(res, "progress", last_progress)
        if not hasattr(res, "job_id"):
            setattr(res, "job_id", job_id)
    except Exception:
        pass

    vtt_len = len(getattr(res, "vtt", "") or getattr(res, "content", "") or "")
    meta_lang = getattr(res, "detected_lang", None)
    print(f"[YTCMS] result received video_id={video_id} job_id={job_id} vtt_len={vtt_len} detected_lang={meta_lang} percent={last_percent} progress={last_progress:.3f}")

    return res