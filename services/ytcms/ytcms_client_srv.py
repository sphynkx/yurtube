import os
import time
import grpc
from typing import Optional, Tuple, Any, Dict, List

from grpc_health.v1 import health_pb2, health_pb2_grpc  # type: ignore

from config.ytcms.ytcms_cfg import (
    load_ytcms_config,
    YTCMS_TOKEN,
    YTCMS_DEFAULT_LANG,
    YTCMS_DEFAULT_TASK,
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


def submit_storage_job(
    *,
    video_id: str,
    storage_rel: str,
    lang: Optional[str] = None,
    task: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    submit_timeout: float = YTCMS_SUBMIT_TIMEOUT,
) -> Tuple[str, str]:
    addr = pick_ytcms_server_addr()
    lang2 = (lang or YTCMS_DEFAULT_LANG).strip() or "auto"
    task2 = (task or YTCMS_DEFAULT_TASK).strip() or "transcribe"

    storage_rel_n = (storage_rel or "").replace("\\", "/").strip().lstrip("/")
    source_rel_path = f"{storage_rel_n}/original.webm"
    output_base_rel_dir = f"{storage_rel_n}/captions"

    idem = (idempotency_key or f"yurtube:{video_id}:{task2}:{lang2}:{source_rel_path}").strip()

    md = _auth_md()
    channel = grpc.insecure_channel(addr)
    stub = ytcms_pb2_grpc.CaptionsServiceStub(channel)

    try:
        req = ytcms_pb2.SubmitJobRequest(
            video_id=video_id,
            idempotency_key=idem,
            lang=lang2,
            task=task2,
            source=ytcms_pb2.SourceRef(
                storage=ytcms_pb2.StorageRef(
                    address=str(YTSTORAGE_GRPC_ADDRESS),
                    tls=bool(YTSTORAGE_GRPC_TLS),
                    token=str(YTSTORAGE_GRPC_TOKEN or ""),
                ),
                rel_path=source_rel_path,
                mime="video/webm",
                filename="original.webm",
            ),
            output=ytcms_pb2.OutputRef(
                storage=ytcms_pb2.StorageRef(
                    address=str(YTSTORAGE_GRPC_ADDRESS),
                    tls=bool(YTSTORAGE_GRPC_TLS),
                    token=str(YTSTORAGE_GRPC_TOKEN or ""),
                ),
                base_rel_dir=output_base_rel_dir,
            ),
        )

        ack = stub.SubmitJob(req, metadata=md, timeout=submit_timeout)
        if not ack.accepted:
            raise RuntimeError(f"Submit rejected: {ack.message}")
        if not ack.job_id:
            raise RuntimeError("Submit returned empty job_id")

        return ack.job_id, addr
    finally:
        try:
            channel.close()
        except Exception:
            pass


def get_status(*, job_id: str, server_addr: str, timeout: float = YTCMS_STATUS_TIMEOUT) -> ytcms_pb2.JobStatus:
    md = _auth_md()
    channel = grpc.insecure_channel(server_addr)
    stub = ytcms_pb2_grpc.CaptionsServiceStub(channel)
    try:
        rep = stub.GetStatus(ytcms_pb2.GetStatusRequest(job_id=job_id), metadata=md, timeout=timeout)
        return rep.status
    finally:
        try:
            channel.close()
        except Exception:
            pass


def get_result(*, job_id: str, server_addr: str, timeout: float = YTCMS_RESULT_TIMEOUT) -> ytcms_pb2.JobResult:
    md = _auth_md()
    channel = grpc.insecure_channel(server_addr)
    stub = ytcms_pb2_grpc.CaptionsServiceStub(channel)
    try:
        return stub.GetResult(ytcms_pb2.GetResultRequest(job_id=job_id), metadata=md, timeout=timeout)
    finally:
        try:
            channel.close()
        except Exception:
            pass


def delete_captions(*, storage_rel: str, server_addr: Optional[str] = None, timeout: float = 30.0) -> None:
    addr = server_addr or pick_ytcms_server_addr()
    md = _auth_md()
    channel = grpc.insecure_channel(addr)
    stub = ytcms_pb2_grpc.CaptionsServiceStub(channel)

    storage_rel_n = (storage_rel or "").replace("\\", "/").strip().lstrip("/")
    try:
        rep = stub.DeleteCaptions(
            ytcms_pb2.DeleteCaptionsRequest(
                storage=ytcms_pb2.StorageRef(
                    address=str(YTSTORAGE_GRPC_ADDRESS),
                    tls=bool(YTSTORAGE_GRPC_TLS),
                    token=str(YTSTORAGE_GRPC_TOKEN or ""),
                ),
                storage_rel=storage_rel_n,
            ),
            metadata=md,
            timeout=timeout,
        )
        if not rep.ok:
            raise RuntimeError(rep.message or "DeleteCaptions failed")
    finally:
        try:
            channel.close()
        except Exception:
            pass


def poll_until_done(
    *,
    job_id: str,
    server_addr: str,
    timeout_sec: float = 600.0,
    poll_interval_sec: float = 1.0,
) -> ytcms_pb2.JobResult:
    deadline = time.time() + float(timeout_sec)
    while time.time() < deadline:
        st = get_status(job_id=job_id, server_addr=server_addr)
        if st.state in (st.DONE, st.FAILED, st.CANCELED):
            break
        time.sleep(float(poll_interval_sec))
    return get_result(job_id=job_id, server_addr=server_addr)