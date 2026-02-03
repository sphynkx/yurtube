from __future__ import annotations

import asyncio
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
from utils.ytconvert.variants_ut import expand_requested_variant_ids


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
    vid = (variant_id or "").strip()
    parts = vid.split(":")
    out: Dict[str, Any] = {"variant_id": vid, "type": parts[0] if parts else ""}

    if out["type"] == "v":
        if len(parts) >= 2:
            out["preset"] = parts[1]
        if len(parts) >= 3:
            cc = parts[2].split("+")
            out["vcodec"] = cc[0] if cc else ""
            out["acodec"] = cc[1] if len(cc) > 1 else ""
        if len(parts) >= 4:
            out["container"] = parts[3]
    elif out["type"] == "a":
        if len(parts) >= 2:
            out["audio_bitrate"] = parts[1]
        if len(parts) >= 3:
            out["acodec"] = parts[2]
        if len(parts) >= 4:
            out["container"] = parts[3]
    return out


def _variant_specs_for_service(requested_variant_ids: List[str]) -> List[ytconvert_pb2.VariantSpec]:
    out: List[ytconvert_pb2.VariantSpec] = []
    for vid in requested_variant_ids:
        vid = (vid or "").strip()
        if vid:
            out.append(ytconvert_pb2.VariantSpec(variant_id=vid))
    return out


def _bool_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _get_storage_grpc_ref(storage_client: StorageClient) -> Dict[str, object]:
    """
    Provide StorageRef for ytconvert service.
    We can't reliably introspect StorageClient, so we use env fallbacks.
    """
    addr = (os.getenv("YTSTORAGE_GRPC_ADDRESS") or "").strip()
    token = (os.getenv("YTSTORAGE_GRPC_TOKEN") or "").strip()
    tls = _bool_env("YTSTORAGE_GRPC_TLS", False)

    if not addr:
        # common local default; adjust if you want hard fail instead
        addr = "127.0.0.1:9092"

    return {"address": addr, "token": token, "tls": tls}


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

        requested_variant_ids = expand_requested_variant_ids(requested_variant_ids)

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

        storage_ref = _get_storage_grpc_ref(storage_client)

        source_rel_path = original_rel_path  # already full rel path in storage
        output_base_rel_dir = storage_rel    # same folder as original (as requested)

        async with grpc.aio.insecure_channel(srv.hostport) as channel:
            stub = ytconvert_pb2_grpc.ConverterStub(channel)

            submit_req = ytconvert_pb2.SubmitConvertRequest(
                video_id=video_id,
                idempotency_key=f"yurtube:{video_id}:{local_job_id}",
                source=ytconvert_pb2.SourceRef(
                    storage=ytconvert_pb2.StorageRef(
                        address=str(storage_ref.get("address") or ""),
                        tls=bool(storage_ref.get("tls") or False),
                        token=str(storage_ref.get("token") or ""),
                    ),
                    rel_path=source_rel_path,
                ),
                output=ytconvert_pb2.OutputRef(
                    storage=ytconvert_pb2.StorageRef(
                        address=str(storage_ref.get("address") or ""),
                        tls=bool(storage_ref.get("tls") or False),
                        token=str(storage_ref.get("token") or ""),
                    ),
                    base_rel_dir=output_base_rel_dir,
                ),
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
                state="QUEUED",
                message="Queued",
                meta={
                    "ack_meta": _struct_to_dict(ack.meta),
                    "storage_address": storage_ref.get("address"),
                    "source_rel_path": source_rel_path,
                    "output_base_rel_dir": output_base_rel_dir,
                },
            )

            # Watch progress
            watch_req = ytconvert_pb2.WatchJobRequest(job_id=grpc_job_id, send_initial=True)
            final_state = None
            async for ev in stub.WatchJob(watch_req, metadata=md):
                if ev.status and ev.status.job_id:
                    st = ev.status
                    final_state = st.state
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

            # Fetch final result
            res = await stub.GetResult(ytconvert_pb2.GetResultRequest(job_id=grpc_job_id), metadata=md, timeout=60.0)
            if res.state != ytconvert_pb2.Status.DONE:
                err_msg = res.message or (res.error.message if res.error else "") or f"ytconvert failed (state={res.state})"
                await set_ytconvert_job_failed(conn, local_job_id, message=err_msg, meta={"result_meta": _struct_to_dict(res.meta)})
                return

            persisted: List[Dict[str, Any]] = []

            for variant_id, vres in res.results_by_variant_id.items():
                parsed = _parse_variant_id(variant_id)

                for art in vres.artifacts:
                    if art.artifact_id != "main":
                        continue

                    rel_path = getattr(art, "rel_path", "") or ""
                    if not rel_path:
                        await set_ytconvert_job_failed(
                            conn,
                            local_job_id,
                            message="ytconvert returned artifact without rel_path",
                            meta={"variant_id": variant_id, "artifact": str(art)},
                        )
                        return

                    # Persist to DB (video -> video_renditions, audio-only -> video_assets)
                    if parsed.get("type") == "v":
                        await upsert_video_rendition(
                            conn,
                            video_id=video_id,
                            preset=str(parsed.get("preset") or "unknown"),
                            codec=str(parsed.get("vcodec") or "unknown"),
                            status="ready",
                            storage_path=rel_path,
                            error_message=None,
                        )
                    elif parsed.get("type") == "a":
                        asset_type = f"ytconvert_audio_main_{parsed.get('audio_bitrate') or ''}_{parsed.get('acodec') or ''}_{parsed.get('container') or ''}".strip("_")
                        asset_type = re.sub(r"[^a-zA-Z0-9._-]+", "_", asset_type)[:64]
                        await upsert_video_asset_path(conn, video_id=video_id, asset_type=asset_type, path=rel_path)

                    persisted.append(
                        {
                            "variant_id": variant_id,
                            "artifact_id": art.artifact_id,
                            "filename": art.filename,
                            "mime": art.mime,
                            "size_bytes": int(art.size_bytes or 0),
                            "sha256": (art.sha256.hex() if art.sha256 else ""),
                            "storage_rel": rel_path,
                        }
                    )

            await set_ytconvert_job_done(conn, local_job_id, message="Done", meta={"persisted": persisted, "final_state": str(final_state)})

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