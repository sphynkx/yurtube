from __future__ import annotations

import asyncio
import inspect
import os
from typing import Any, Dict, List, Optional

import grpc
from google.protobuf.json_format import MessageToDict

from config.ytconvert.ytconvert_cfg import load_ytconvert_config
from db import get_conn, release_conn
from db.ytconvert.ytconvert_jobs_db import (
    set_ytconvert_job_failed,
    set_ytconvert_job_grpc_id,
    set_ytconvert_job_done,
    update_ytconvert_job_state,
)
from services.ytconvert.ytconvert_pick_server_srv import pick_server_with_healthcheck
from services.ytconvert.ytconvert_proto import ytconvert_pb2, ytconvert_pb2_grpc
from services.ytstorage.base_srv import StorageClient


def _auth_md(token: Optional[str]) -> List[tuple]:
    if not token:
        return []
    return [("authorization", f"Bearer {token}")]


def _struct_to_dict(s) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    try:
        return MessageToDict(s, preserving_proto_field_name=True)
    except Exception:
        # last resort: stringify
        return {"_raw": str(s)}


async def _iter_storage_bytes(storage: StorageClient, rel_path: str) -> bytes:
    reader_ctx = storage.open_reader(rel_path)
    if inspect.isawaitable(reader_ctx):
        reader_ctx = await reader_ctx

    if hasattr(reader_ctx, "__aiter__") or hasattr(reader_ctx, "__anext__"):
        async for chunk in reader_ctx:
            if chunk:
                yield bytes(chunk)
        return

    for chunk in reader_ctx:
        if chunk:
            yield bytes(chunk)


def _variant_specs_for_service(requested_variant_ids: List[str]) -> List[ytconvert_pb2.VariantSpec]:
    out: List[ytconvert_pb2.VariantSpec] = []
    for vid in requested_variant_ids:
        vid = (vid or "").strip()
        if vid:
            out.append(ytconvert_pb2.VariantSpec(variant_id=vid))
    return out


async def _run_job(
    *,
    storage_client: StorageClient,
    local_job_id: str,
    video_id: str,
    original_rel_path: str,
    requested_variant_ids: List[str],
) -> None:
    conn = await get_conn()
    try:
        cfg = load_ytconvert_config()
        if not cfg.grpc_plaintext:
            raise RuntimeError("YTCONVERT_GRPC_PLAINTEXT=false is not supported yet")

        srv = await pick_server_with_healthcheck()
        md = _auth_md(srv.token)

        await update_ytconvert_job_state(
            conn,
            local_job_id,
            state="SUBMITTING",
            progress_percent=0,
            message="Submitting to ytconvert",
            meta={"server": srv.hostport},
        )

        async with grpc.aio.insecure_channel(srv.hostport) as channel:
            stub = ytconvert_pb2_grpc.ConverterStub(channel)

            # 1) SubmitConvert
            submit_req = ytconvert_pb2.SubmitConvertRequest(
                video_id=video_id,
                idempotency_key=f"yurtube:{video_id}:{local_job_id}",
                variants=_variant_specs_for_service(requested_variant_ids),
            )
            ack = await stub.SubmitConvert(submit_req, metadata=md, timeout=10.0)
            if not ack.accepted:
                await set_ytconvert_job_failed(
                    conn,
                    local_job_id,
                    message=f"Rejected: {ack.message}",
                    meta={"ack_meta": _struct_to_dict(ack.meta)},
                )
                return

            grpc_job_id = ack.job_id
            await set_ytconvert_job_grpc_id(
                conn,
                local_job_id,
                grpc_job_id=grpc_job_id,
                state="WAITING_UPLOAD",
                message="Job created, uploading source",
                meta={"ack_meta": _struct_to_dict(ack.meta)},
            )

            # 2) UploadSource
            filename = os.path.basename(original_rel_path) or "original.webm"

            async def gen_upload():
                offset = 0
                first = True
                async for data in _iter_storage_bytes(storage_client, original_rel_path):
                    ch = ytconvert_pb2.UploadSourceChunk(
                        job_id=grpc_job_id,
                        offset=offset,
                        data=data,
                        last=False,
                    )
                    if first:
                        ch.filename = filename
                        ch.content_type = "video/webm"
                        first = False
                    yield ch
                    offset += len(data)

                yield ytconvert_pb2.UploadSourceChunk(job_id=grpc_job_id, offset=offset, data=b"", last=True)

            up = await stub.UploadSource(gen_upload(), metadata=md, timeout=cfg.upload_timeout_sec)
            if not up.accepted:
                await set_ytconvert_job_failed(
                    conn,
                    local_job_id,
                    message=f"Upload rejected: {up.message}",
                    meta={"upload_meta": _struct_to_dict(up.meta)},
                )
                return

            await update_ytconvert_job_state(
                conn,
                local_job_id,
                state="RUNNING",
                progress_percent=0,
                message="Converting",
                meta={"upload_meta": _struct_to_dict(up.meta)},
            )

            # 3) WatchJob until terminal status
            final_state = None
            last_status_meta = None
            watch_req = ytconvert_pb2.WatchJobRequest(job_id=grpc_job_id, send_initial=True)

            async for ev in stub.WatchJob(watch_req, metadata=md):
                if not ev.status.job_id:
                    continue

                st = ev.status
                last_status_meta = _struct_to_dict(st.meta)

                await update_ytconvert_job_state(
                    conn,
                    local_job_id,
                    state=ytconvert_pb2.Status.State.Name(st.state),
                    progress_percent=int(st.percent or 0),
                    message=st.message,
                    meta={"status_meta": last_status_meta} if last_status_meta else None,
                )

                if st.state in (ytconvert_pb2.Status.DONE, ytconvert_pb2.Status.FAILED, ytconvert_pb2.Status.CANCELED):
                    final_state = st.state
                    break

            # If WatchJob yielded nothing at all (shouldn't normally happen), still try GetResult
            res = await stub.GetResult(ytconvert_pb2.GetResultRequest(job_id=grpc_job_id), metadata=md, timeout=30.0)

            if res.state == ytconvert_pb2.Status.DONE:
                summary = {
                    "variants": list(res.results_by_variant_id.keys()),
                }
                await set_ytconvert_job_done(
                    conn,
                    local_job_id,
                    message=res.message or "DONE",
                    meta={
                        "result_summary": summary,
                        "result_meta": _struct_to_dict(res.meta),
                    },
                )
            else:
                err_msg = res.message or (res.error.message if res.error else "") or f"ytconvert failed (state={res.state})"
                await set_ytconvert_job_failed(
                    conn,
                    local_job_id,
                    message=err_msg,
                    meta={
                        "result_meta": _struct_to_dict(res.meta),
                        "error": {
                            "code": (res.error.code if res.error else ""),
                            "message": (res.error.message if res.error else ""),
                            "meta": _struct_to_dict(res.error.meta) if (res.error and res.error.meta) else None,
                        } if res.error else None,
                        "final_state": int(final_state) if final_state is not None else None,
                        "last_status_meta": last_status_meta,
                    },
                )

    except Exception as e:
        await set_ytconvert_job_failed(
            conn,
            local_job_id,
            message=f"ytconvert integration error: {e}",
            meta={"exc": repr(e)},
        )
    finally:
        await release_conn(conn)


def schedule_ytconvert_job(
    *,
    request,
    local_job_id: str,
    video_id: str,
    storage_rel: str,  # reserved for next stage (download results)
    original_rel_path: str,
    requested_variant_ids: List[str],
) -> None:
    storage_client: StorageClient = request.app.state.storage
    asyncio.create_task(
        _run_job(
            storage_client=storage_client,
            local_job_id=local_job_id,
            video_id=video_id,
            original_rel_path=original_rel_path,
            requested_variant_ids=requested_variant_ids,
        )
    )