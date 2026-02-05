import os
import time
import grpc
from typing import Optional, Tuple, Callable, Any, Dict, List

from grpc_health.v1 import health_pb2, health_pb2_grpc  # type: ignore

from config.ytcms.ytcms_cfg import (
    load_ytcms_config,
    YTCMS_TOKEN,
    YTCMS_DEFAULT_LANG,
    YTCMS_DEFAULT_TASK,
    YTCMS_POLL_INTERVAL,
    YTCMS_SUBMIT_TIMEOUT,
    YTCMS_STATUS_TIMEOUT,
    YTCMS_RESULT_TIMEOUT,
)

from config.ytstorage.ytstorage_cfg import (
    YTSTORAGE_GRPC_ADDRESS,
    YTSTORAGE_GRPC_TLS,
    YTSTORAGE_GRPC_TOKEN,
)

from services.ytcms.ytcms_proto import ytcms_pb2, ytcms_pb2_grpc


_YTCMS_HEALTH_TIMEOUT_SEC = float((os.getenv("YTCMS_HEALTH_TIMEOUT", "") or "0.7").strip() or "0.7")
_YTCMS_SERVER_TTL_SEC = float((os.getenv("YTCMS_SERVER_TTL", "") or "10").strip() or "10")
_last_good: Dict[str, Any] = {"addr": None, "ts": 0.0}


def _auth_md() -> List[Tuple[str, str]]:
    tok = (YTCMS_TOKEN or "").strip()
    if not tok:
        return []
    return [("authorization", f"Bearer {tok}")]


def _healthcheck_addr(addr: str) -> bool:
    channel = grpc.insecure_channel(addr)
    try:
        stub = health_pb2_grpc.HealthStub(channel)
        md = _auth_md()

        try:
            resp = stub.Check(
                health_pb2.HealthCheckRequest(service="ytcms.v1.CaptionsService"),
                metadata=md,
                timeout=_YTCMS_HEALTH_TIMEOUT_SEC,
            )
            if resp.status == health_pb2.HealthCheckResponse.SERVING:
                return True
        except Exception:
            pass

        try:
            resp2 = stub.Check(
                health_pb2.HealthCheckRequest(service=""),
                metadata=md,
                timeout=_YTCMS_HEALTH_TIMEOUT_SEC,
            )
            return resp2.status == health_pb2.HealthCheckResponse.SERVING
        except Exception:
            return False
    finally:
        try:
            channel.close()
        except Exception:
            pass


def pick_ytcms_server_addr() -> str:
    cfg = load_ytcms_config()
    servers = list(cfg.servers or [])
    if not servers:
        return f"{cfg.host}:{cfg.port}"

    now = time.time()
    cached = _last_good.get("addr")
    ts = float(_last_good.get("ts") or 0.0)
    if cached and (now - ts) < _YTCMS_SERVER_TTL_SEC:
        return str(cached)

    for s in servers:
        addr = f"{s.host}:{s.port}"
        try:
            if _healthcheck_addr(addr):
                _last_good["addr"] = addr
                _last_good["ts"] = now
                return addr
        except Exception:
            continue

    addr0 = f"{servers[0].host}:{servers[0].port}"
    _last_good["addr"] = addr0
    _last_good["ts"] = now
    return addr0


def submit_storage_job_and_wait(
    *,
    video_id: str,
    source_rel_path: str,
    output_base_rel_dir: str,
    lang: Optional[str] = None,
    task: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    poll_interval: float = YTCMS_POLL_INTERVAL,
    submit_timeout: float = YTCMS_SUBMIT_TIMEOUT,
    status_timeout: float = YTCMS_STATUS_TIMEOUT,
    result_timeout: float = YTCMS_RESULT_TIMEOUT,
    on_status: Optional[Callable[[str, str, str, int], None]] = None,
) -> Tuple[ytcms_pb2.JobResult, str]:
    """
    Storage-driven workflow:
    - SubmitJob(video_id, source storage ref+rel_path, output base dir)
    - WatchJob updates -> on_status(video_id, job_id, state_name, percent)
    - GetResult returns storage paths to vtt/meta
    Returns (result, job_server_addr)
    """
    addr = pick_ytcms_server_addr()
    lang = (lang or YTCMS_DEFAULT_LANG).strip() or "auto"
    task = (task or YTCMS_DEFAULT_TASK).strip() or "transcribe"
    idem = (idempotency_key or f"yurtube:{video_id}:{task}:{lang}:{source_rel_path}").strip()

    md = _auth_md()
    channel = grpc.insecure_channel(addr)
    stub = ytcms_pb2_grpc.CaptionsServiceStub(channel)

    try:
        req = ytcms_pb2.SubmitJobRequest(
            video_id=video_id,
            idempotency_key=idem,
            lang=lang,
            task=task,
            source=ytcms_pb2.SourceRef(
                storage=ytcms_pb2.StorageRef(
                    address=str(YTSTORAGE_GRPC_ADDRESS),
                    tls=bool(YTSTORAGE_GRPC_TLS),
                    token=str(YTSTORAGE_GRPC_TOKEN or ""),
                ),
                rel_path=source_rel_path.lstrip("/"),
                mime="video/webm",
                filename=os.path.basename(source_rel_path) or "original.webm",
            ),
            output=ytcms_pb2.OutputRef(
                storage=ytcms_pb2.StorageRef(
                    address=str(YTSTORAGE_GRPC_ADDRESS),
                    tls=bool(YTSTORAGE_GRPC_TLS),
                    token=str(YTSTORAGE_GRPC_TOKEN or ""),
                ),
                base_rel_dir=output_base_rel_dir.lstrip("/"),
            ),
        )

        ack = stub.SubmitJob(req, metadata=md, timeout=submit_timeout)
        if not ack.accepted:
            raise RuntimeError(f"Submit rejected: {ack.message}")

        job_id = ack.job_id

        def _emit(state_name: str, percent: int):
            try:
                if on_status:
                    on_status(video_id, job_id, state_name, int(percent))
            except Exception:
                pass

        # watch until final
        watch_req = ytcms_pb2.WatchJobRequest(job_id=job_id, send_initial=True)
        last_state = ""
        last_percent = -1
        for ev in stub.WatchJob(watch_req, metadata=md, timeout=status_timeout):
            st = ev.status
            if not st or not st.job_id:
                continue
            state_name = ytcms_pb2.JobStatus.State.Name(st.state)
            pct = int(st.percent or 0)

            if state_name != last_state or pct != last_percent:
                _emit(state_name, pct)
                last_state, last_percent = state_name, pct

            if st.state in (ytcms_pb2.JobStatus.DONE, ytcms_pb2.JobStatus.FAILED, ytcms_pb2.JobStatus.CANCELED):
                break

        res = stub.GetResult(ytcms_pb2.GetResultRequest(job_id=job_id), metadata=md, timeout=result_timeout)
        return res, addr
    finally:
        try:
            channel.close()
        except Exception:
            pass