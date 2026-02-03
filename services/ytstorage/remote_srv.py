"""
RemoteStorageClient: gRPC-based storage provider.
"""
import os
import asyncio
from typing import AsyncIterator, List, Optional, Dict, Any

import grpc

from config.config import settings
from config.ytstorage.ytstorage_cfg import (
    YTSTORAGE_GRPC_ADDRESS,
    YTSTORAGE_GRPC_TLS,
    YTSTORAGE_GRPC_TOKEN,
    YTSTORAGE_BASE_PREFIX,
    YTSTORAGE_GRPC_MAX_MSG_MB,
)
from services.ytstorage.base_srv import StorageClient

# Generated stubs
from services.ytstorage.ytstorage_proto import ytstorage_pb2 as pb
from services.ytstorage.ytstorage_proto import ytstorage_pb2_grpc as pb_grpc


def _norm(rel: str) -> str:
    return (rel or "").strip().replace("\\", "/").lstrip("/")


def _cfg_str(name: str, default: str) -> str:
    v = getattr(settings, name, None)
    if isinstance(v, str) and v.strip() != "":
        return v.strip()
    env = os.getenv(name)
    if isinstance(env, str) and env.strip() != "":
        return env.strip()
    return default


def _cfg_bool(name: str, default: bool) -> bool:
    v = getattr(settings, name, None)
    if isinstance(v, bool):
        return v
    env = os.getenv(name)
    if env is None or env == "":
        return default
    return env.lower() in ("1", "true", "yes", "on")


def _cfg_int(name: str, default: int) -> int:
    v = getattr(settings, name, None)
    if isinstance(v, int):
        return v
    env = os.getenv(name)
    if env is None or env == "":
        return default
    try:
        return int(env)
    except Exception:
        return default


def _auth_md() -> List[tuple]:
    tok = _cfg_str("YTSTORAGE_GRPC_TOKEN", YTSTORAGE_GRPC_TOKEN)
    if tok:
        return [("authorization", f"Bearer {tok}")]
    return []


def _grpc_channel() -> grpc.aio.Channel:
    target = _cfg_str("YTSTORAGE_GRPC_ADDRESS", YTSTORAGE_GRPC_ADDRESS)
    use_tls = _cfg_bool("YTSTORAGE_GRPC_TLS", bool(YTSTORAGE_GRPC_TLS))
    max_mb = _cfg_int("YTSTORAGE_GRPC_MAX_MSG_MB", int(YTSTORAGE_GRPC_MAX_MSG_MB))
    max_msg = int(max_mb) * 1024 * 1024
    opts = [
        ("grpc.max_send_message_length", max_msg),
        ("grpc.max_receive_message_length", max_msg),
    ]
    if use_tls:
        creds = grpc.ssl_channel_credentials()
        return grpc.aio.secure_channel(target, creds, options=opts)
    return grpc.aio.insecure_channel(target, options=opts)


class _AsyncWriter:
    """
    Async writer helper:
    - async with client.open_writer(path) as w: await w.write(...); ...
    - bidirectional stream: header -> data chunks; server streams acks
    """
    def __init__(self, stub: pb_grpc.StorageServiceStub, path: str, overwrite: bool, append: bool, md: List[tuple]):
        self._stub = stub
        self._path = path
        self._overwrite = overwrite
        self._append = append
        self._md = md
        self._q: asyncio.Queue = asyncio.Queue()
        self._acks: List[pb.WriteAck] = []
        self._done = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._err: Optional[Exception] = None

    async def __aenter__(self):
        async def _producer():
            header = pb.WriteHeader(
                path=pb.Path(rel_path=self._path),
                overwrite=self._overwrite,
                append=self._append,
                expected_size=0,
            )
            yield pb.WriteEnvelope(header=header)
            while True:
                item = await self._q.get()
                if item is None:
                    break
                yield pb.WriteEnvelope(data=pb.WriteData(data=item))

        async def _runner():
            try:
                async for ack in self._stub.Write(_producer(), metadata=self._md):
                    self._acks.append(ack)
                self._done.set()
            except Exception as e:
                self._err = e
                self._done.set()

        self._task = asyncio.create_task(_runner())
        return self

    async def write(self, data: bytes) -> None:
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("write() expects bytes")
        await self._q.put(bytes(data))

    async def __aexit__(self, exc_type, exc, tb):
        await self._q.put(None)
        await self._done.wait()
        if self._task:
            try:
                await self._task
            except Exception:
                pass
        if self._err:
            raise self._err
        if self._acks:
            last = self._acks[-1]
            if not last.ok:
                raise RuntimeError(f"remote write failed: {last.error or 'unknown error'}")


class RemoteStorageClient(StorageClient):
    """
    Remote storage provider.
    Note about_abs(): for remote storage it returns logical abs path with prefix YTSTORAGE_BASE_PREFIX.
    """
    def __init__(self) -> None:
        self._channel = _grpc_channel()
        self._stub = pb_grpc.StorageServiceStub(self._channel)
        self._base_prefix = _cfg_str("YTSTORAGE_BASE_PREFIX", YTSTORAGE_BASE_PREFIX)

    def join(self, base: str, *parts: str) -> str:
        p = "/".join([_norm(base)] + [_norm(x) for x in parts])
        return p.replace("//", "/")

    def to_abs(self, rel_path: str) -> str:
        rp = _norm(rel_path)
        if self._base_prefix:
            return f"{self._base_prefix}/{rp}".replace("//", "/")
        return rp

    async def exists(self, rel_path: str) -> bool:
        req = pb.ExistsRequest(path=pb.Path(rel_path=_norm(rel_path)))
        try:
            resp = await self._stub.Exists(req, metadata=_auth_md())
            return bool(resp.exists)
        except grpc.RpcError:
            return False

    async def stat(self, rel_path: str) -> Dict[str, Any]:
        resp = await self._stub.Stat(pb.StatRequest(path=pb.Path(rel_path=_norm(rel_path))), metadata=_auth_md())
        return {
            "name": resp.name,
            "rel_path": resp.rel_path,
            "file_type": int(resp.file_type),
            "size_bytes": int(resp.size_bytes),
            "created_at_ms": int(resp.created_at_ms),
            "updated_at_ms": int(resp.updated_at_ms),
            "etag": resp.etag or None,
        }

    async def mkdirs(self, rel_path: str, exist_ok: bool = True) -> None:
        await self._stub.Mkdirs(pb.MkdirsRequest(path=pb.Path(rel_path=_norm(rel_path)), exist_ok=bool(exist_ok)), metadata=_auth_md())

    async def listdir(self, rel_path: str, recursive: bool = False, limit: int = 0, page_token: str = "") -> Dict[str, Any]:
        resp = await self._stub.Listdir(
            pb.ListdirRequest(
                path=pb.Path(rel_path=_norm(rel_path)),
                recursive=bool(recursive),
                limit=int(limit or 0),
                page_token=page_token or "",
            ),
            metadata=_auth_md(),
        )
        entries = []
        for e in resp.entries:
            entries.append({
                "name": e.name,
                "rel_path": e.rel_path,
                "file_type": int(e.file_type),
                "size_bytes": int(e.size_bytes),
                "created_at_ms": int(e.created_at_ms),
                "updated_at_ms": int(e.updated_at_ms),
            })
        return {"entries": entries, "next_page_token": resp.next_page_token or ""}

    async def rename(self, src_rel: str, dst_rel: str, overwrite: bool = False) -> None:
        resp = await self._stub.Rename(
            pb.RenameRequest(
                src=pb.Path(rel_path=_norm(src_rel)),
                dst=pb.Path(rel_path=_norm(dst_rel)),
                overwrite=bool(overwrite),
            ),
            metadata=_auth_md(),
        )
        if not resp.ok:
            raise RuntimeError("remote rename failed")

    async def remove(self, rel_path: str, recursive: bool = False) -> None:
        resp = await self._stub.Remove(pb.RemoveRequest(path=pb.Path(rel_path=_norm(rel_path)), recursive=bool(recursive)), metadata=_auth_md())
        if not resp.ok:
            raise RuntimeError("remote remove failed")

    async def open_reader(self, rel_path: str, offset: int = 0, length: int = -1) -> AsyncIterator[bytes]:
        stream = self._stub.Read(
            pb.ReadRequest(
                path=pb.Path(rel_path=_norm(rel_path)),
                offset=int(offset or 0),
                length=int(length if length is not None else -1),
            ),
            metadata=_auth_md(),
        )

        async def _aiter():
            async for chunk in stream:
                yield bytes(chunk.data or b"")

        return _aiter()

    async def open_writer(self, rel_path: str, overwrite: bool = True, append: bool = False):
        return _AsyncWriter(self._stub, _norm(rel_path), overwrite, append, _auth_md())

    async def enqueue_put(self, rel_path: str, expected_size: int = 0, overwrite: bool = True) -> str:
        ref = await self._stub.EnqueuePut(
            pb.EnqueuePutRequest(path=pb.Path(rel_path=_norm(rel_path)), overwrite=bool(overwrite), expected_size=int(expected_size or 0)),
            metadata=_auth_md(),
        )
        return ref.job_id or ""

    async def enqueue_get(self, rel_path: str) -> str:
        ref = await self._stub.EnqueueGet(pb.EnqueueGetRequest(path=pb.Path(rel_path=_norm(rel_path))), metadata=_auth_md())
        return ref.job_id or ""

    async def job_status(self, job_id: str) -> Dict[str, Any]:
        resp = await self._stub.JobStatus(pb.JobStatusRequest(job_id=job_id or ""), metadata=_auth_md())
        return {
            "status": int(resp.status),
            "percent": int(resp.percent),
            "bytes_processed": int(resp.bytes_processed),
            "error": resp.error or "",
        }

    async def cancel_job(self, job_id: str) -> bool:
        resp = await self._stub.CancelJob(pb.CancelJobRequest(job_id=job_id or ""), metadata=_auth_md())
        return bool(resp.ok)

    async def health(self) -> Dict[str, str]:
        resp = await self._stub.Health(pb.HealthRequest(), metadata=_auth_md())
        return {"status": resp.status, "version": resp.version}