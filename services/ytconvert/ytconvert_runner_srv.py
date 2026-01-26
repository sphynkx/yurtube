from __future__ import annotations

import asyncio
import inspect
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import grpc
from google.protobuf.json_format import MessageToDict

from config.ytconvert.ytconvert_cfg import load_ytconvert_config
from db import get_conn, release_conn
from db.ytconvert.video_assets_db import upsert_video_asset_path
from db.ytconvert.video_renditions_db import upsert_video_rendition
from db.ytconvert.ytconvert_jobs_db import (
    set_ytconvert_job_failed,
    set_ytconvert_job_grpc_id,
    set_ytconvert_job_done,
    update_ytconvert_job_state,
)
from services.ytconvert.ytconvert_pick_server_srv import pick_server_with_healthcheck
from services.ytconvert.ytconvert_proto import ytconvert_pb2, ytconvert_pb2_grpc
from services.ytstorage.base_srv import StorageClient


def _auth_md(token: Optional[str]) -> List[Tuple[str, str]]:
    if not token:
        return []
    return [("authorization", f"Bearer {token}")]


def _struct_to_dict(s) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    try:
        return MessageToDict(s, preserving_proto_field_name=True)
    except Exception:
        return {"_raw": str(s)}


def _parse_variant_id(variant_id: str) -> Dict[str, Any]:
    """
    Best-effort parsing from variant_id like:
      v:1080p:h264+aac:mp4
      a:128k:aac:m4a
    """
    vid = (variant_id or "").strip()
    parts = vid.split(":")
    out: Dict[str, Any] = {"variant_id": vid, "type": parts[0] if parts else ""}

    if out["type"] == "v":
        if len(parts) >= 2:
            out["preset"] = parts[1]  # e.g. 1080p
        if len(parts) >= 3:
            cc = parts[2].split("+")  # h264+aac
            out["vcodec"] = cc[0] if cc else ""
            out["acodec"] = cc[1] if len(cc) > 1 else ""
        if len(parts) >= 4:
            out["container"] = parts[3]
    elif out["type"] == "a":
        if len(parts) >= 2:
            out["audio_bitrate"] = parts[1]  # 128k
        if len(parts) >= 3:
            out["acodec"] = parts[2]
        if len(parts) >= 4:
            out["container"] = parts[3]
    return out


async def _iter_storage_bytes(storage: StorageClient, rel_path: str):
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


async def _write_download_to_storage(
    *,
    stub: ytconvert_pb2_grpc.ConverterStub,
    md: List[Tuple[str, str]],
    storage_client: StorageClient,
    job_id: str,
    variant_id: str,
    artifact_id: str,
    out_rel_path: str,
    retries: int = 3,
) -> Dict[str, Any]:
    """
    DownloadResult -> stream write into storage.
    Retries overwrite the file from scratch (StorageClient has no append/seek API).
    """
    last_meta: Dict[str, Any] = {}
    bytes_written = 0

    for attempt in range(1, retries + 1):
        bytes_written = 0
        try:
            writer_ctx = storage_client.open_writer(out_rel_path, overwrite=True)
            if inspect.isawaitable(writer_ctx):
                writer_ctx = await writer_ctx

            req = ytconvert_pb2.DownloadRequest(
                job_id=job_id,
                variant_id=variant_id,
                artifact_id=artifact_id,
                offset=0,
            )
            stream = stub.DownloadResult(req, metadata=md)

            async def _consume():
                nonlocal last_meta, bytes_written
                async for ch in stream:
                    if ch.offset == 0:
                        last_meta = {
                            "filename": ch.filename,
                            "mime": ch.mime,
                            "total_size_bytes": int(ch.total_size_bytes or 0),
                            "sha256_total": ch.sha256_total.hex() if ch.sha256_total else "",
                        }
                    if ch.data:
                        yield ch.data
                    if ch.last:
                        break

            if hasattr(writer_ctx, "__aenter__"):
                async with writer_ctx as f:
                    async for data in _consume():
                        wr = f.write(data)
                        if inspect.isawaitable(wr):
                            await wr
                        bytes_written += len(data)
            else:
                with writer_ctx as f:
                    async for data in _consume():
                        f.write(data)
                        bytes_written += len(data)

            return {"bytes_written": bytes_written, **last_meta}

        except Exception:
            if attempt >= retries:
                raise
            await asyncio.sleep(0.5 * attempt)

    return {"bytes_written": bytes_written, **last_meta}


async def _run_job(
    *,
    storage_client: StorageClient,
    local_job_id: str,
    video_id: str,
    storage_rel: str,
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
                await set_ytconvert_job_failed(conn, local_job_id, message=f"Rejected: {ack.message}", meta={"ack_meta": _struct_to_dict(ack.meta)})
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
                    ch = ytconvert_pb2.UploadSourceChunk(job_id=grpc_job_id, offset=offset, data=data, last=False)
                    if first:
                        ch.filename = filename
                        ch.content_type = "video/webm"
                        first = False
                    yield ch
                    offset += len(data)
                yield ytconvert_pb2.UploadSourceChunk(job_id=grpc_job_id, offset=offset, data=b"", last=True)

            up = await stub.UploadSource(gen_upload(), metadata=md, timeout=cfg.upload_timeout_sec)
            if not up.accepted:
                await set_ytconvert_job_failed(conn, local_job_id, message=f"Upload rejected: {up.message}", meta={"upload_meta": _struct_to_dict(up.meta)})
                return

            await update_ytconvert_job_state(conn, local_job_id, state="RUNNING", progress_percent=0, message="Converting", meta={"upload_meta": _struct_to_dict(up.meta)})

            # 3) WatchJob until terminal status
            watch_req = ytconvert_pb2.WatchJobRequest(job_id=grpc_job_id, send_initial=True)
            async for ev in stub.WatchJob(watch_req, metadata=md):
                if ev.status.job_id:
                    st = ev.status
                    await update_ytconvert_job_state(
                        conn,
                        local_job_id,
                        state=ytconvert_pb2.Status.State.Name(st.state),
                        progress_percent=int(st.percent or 0),
                        message=st.message,
                        meta={"status_meta": _struct_to_dict(st.meta)} if st.meta else None,
                    )
                    if st.state in (ytconvert_pb2.Status.DONE, ytconvert_pb2.Status.FAILED, ytconvert_pb2.Status.CANCELED):
                        break
                elif ev.partial.job_id:
                    pr = ev.partial
                    await update_ytconvert_job_state(
                        conn,
                        local_job_id,
                        state=ytconvert_pb2.Status.State.Name(pr.state),
                        progress_percent=int(pr.percent or 0),
                        message=pr.message,
                        meta={"partial_meta": _struct_to_dict(pr.meta)} if pr.meta else None,
                    )
                    if pr.state in (ytconvert_pb2.Status.DONE, ytconvert_pb2.Status.FAILED, ytconvert_pb2.Status.CANCELED):
                        break

            # 4) GetResult
            res = await stub.GetResult(ytconvert_pb2.GetResultRequest(job_id=grpc_job_id), metadata=md, timeout=60.0)
            if res.state != ytconvert_pb2.Status.DONE:
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
                    },
                )
                return

            # 5) Download artifacts into the same folder as original.webm (no extra subfolders)
            mk = storage_client.mkdirs(storage_rel, exist_ok=True)
            if inspect.isawaitable(mk):
                await mk

            downloaded: List[Dict[str, Any]] = []

            for variant_id, vres in res.results_by_variant_id.items():
                parsed = _parse_variant_id(variant_id)

                for art in vres.artifacts:
                    if art.artifact_id != "main":
                        continue

                    fname = art.filename or "main.bin"
                    out_rel = storage_client.join(storage_rel, fname)

                    print(
                        f"[YTCONVERT] download start video_id={video_id} job_id={grpc_job_id} "
                        f"variant_id={variant_id} artifact_id={art.artifact_id} filename={fname} size={art.size_bytes}"
                    )

                    dl_meta = await _write_download_to_storage(
                        stub=stub,
                        md=md,
                        storage_client=storage_client,
                        job_id=grpc_job_id,
                        variant_id=variant_id,
                        artifact_id=art.artifact_id,
                        out_rel_path=out_rel,
                        retries=3,
                    )

                    print(
                        f"[YTCONVERT] download done video_id={video_id} job_id={grpc_job_id} "
                        f"variant_id={variant_id} artifact_id={art.artifact_id} rel={out_rel} bytes={dl_meta.get('bytes_written')}"
                    )

                    # Persist to DB (video -> video_renditions, audio-only -> video_assets)
                    if parsed.get("type") == "v":
                        preset = str(parsed.get("preset") or "unknown")
                        codec = str(parsed.get("vcodec") or "unknown")
                        await upsert_video_rendition(
                            conn,
                            video_id=video_id,
                            preset=preset,
                            codec=codec,
                            status="ready",
                            storage_path=out_rel,
                            error_message=None,
                        )
                    elif parsed.get("type") == "a":
                        ab = str(parsed.get("audio_bitrate") or "")
                        ac = str(parsed.get("acodec") or "")
                        cont = str(parsed.get("container") or "")
                        asset_type = "ytconvert_audio_main"
                        if ab or ac or cont:
                            asset_type = f"ytconvert_audio_main_{ab}_{ac}_{cont}".strip("_")
                            asset_type = re.sub(r"[^a-zA-Z0-9._-]+", "_", asset_type)[:64]
                        await upsert_video_asset_path(conn, video_id=video_id, asset_type=asset_type, path=out_rel)

                    downloaded.append(
                        {
                            "variant_id": variant_id,
                            "artifact_id": art.artifact_id,
                            "filename": fname,
                            "mime": art.mime,
                            "size_bytes": int(art.size_bytes or 0),
                            "sha256": (art.sha256.hex() if art.sha256 else ""),
                            "storage_rel": out_rel,
                            "download": dl_meta,
                        }
                    )

            await set_ytconvert_job_done(
                conn,
                local_job_id,
                message=res.message or "DONE",
                meta={
                    "result_summary": {"variants": list(res.results_by_variant_id.keys())},
                    "result_meta": _struct_to_dict(res.meta),
                    "downloaded": downloaded,
                },
            )

    except Exception as e:
        await set_ytconvert_job_failed(conn, local_job_id, message=f"ytconvert integration error: {e}", meta={"exc": repr(e)})
    finally:
        await release_conn(conn)


def schedule_ytconvert_job(
    *,
    request,
    local_job_id: str,
    video_id: str,
    storage_rel: str,
    original_rel_path: str,
    requested_variant_ids: List[str],
) -> None:
    storage_client: StorageClient = request.app.state.storage
    asyncio.create_task(
        _run_job(
            storage_client=storage_client,
            local_job_id=local_job_id,
            video_id=video_id,
            storage_rel=storage_rel,
            original_rel_path=original_rel_path,
            requested_variant_ids=requested_variant_ids,
        )
    )