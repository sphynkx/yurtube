from __future__ import annotations

from typing import AsyncIterator, Dict, List, Optional, Tuple

import grpc

from utils.ytconvert.ytconvert_servers_ut import YtconvertServer
from services.ytconvert.ytconvert_proto import ytconvert_pb2, ytconvert_pb2_grpc


def _auth_md(token: Optional[str]) -> List[Tuple[str, str]]:
    if not token:
        return []
    return [("authorization", f"Bearer {token}")]


class YtconvertClient:
    def __init__(self, server: YtconvertServer):
        self.server = server
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[ytconvert_pb2_grpc.ConverterStub] = None

    async def __aenter__(self) -> "YtconvertClient":
        self._channel = grpc.aio.insecure_channel(self.server.hostport)
        self._stub = ytconvert_pb2_grpc.ConverterStub(self._channel)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._channel:
            await self._channel.close()

    @property
    def stub(self) -> ytconvert_pb2_grpc.ConverterStub:
        assert self._stub is not None
        return self._stub

    @property
    def metadata(self) -> List[Tuple[str, str]]:
        return _auth_md(self.server.token)

    async def submit_convert(
        self,
        *,
        video_id: str,
        idempotency_key: str,
        variants: List[Dict[str, object]],
        options: Optional[Dict[str, object]] = None,
        timeout_sec: float = 10.0,
    ) -> ytconvert_pb2.JobAck:
        """
        variants: list of dicts with either full spec fields OR just variant_id.
        This client will send full VariantSpec if provided.
        """
        print(f"[DEBUG] Submitting conversion job: video_id={video_id}, variants={variants}")
        vlist: List[ytconvert_pb2.VariantSpec] = []
        for v in variants:
            vlist.append(
                ytconvert_pb2.VariantSpec(
                    variant_id=str(v.get("variant_id") or ""),
                    label=str(v.get("label") or ""),
                    kind=v.get("kind", ytconvert_pb2.VariantSpec.KIND_UNSPECIFIED),
                    container=str(v.get("container") or ""),
                    height=int(v.get("height") or 0),
                    vcodec=str(v.get("vcodec") or ""),
                    acodec=str(v.get("acodec") or ""),
                    audio_bitrate_kbps=int(v.get("audio_bitrate_kbps") or 0),
                )
            )

        req = ytconvert_pb2.SubmitConvertRequest(
            video_id=video_id,
            idempotency_key=idempotency_key,
            variants=vlist,
        )

        print(f"[DEBUG] Sending SubmitConvertRequest: {req}")
        return await self.stub.SubmitConvert(req, metadata=self.metadata, timeout=timeout_sec)

    async def upload_source(
        self,
        chunks: AsyncIterator[ytconvert_pb2.UploadSourceChunk],
        timeout_sec: float = 600.0,
    ) -> ytconvert_pb2.UploadAck:
        return await self.stub.UploadSource(chunks, metadata=self.metadata, timeout=timeout_sec)

    async def watch_job(
        self,
        job_id: str,
        send_initial: bool = True,
    ) -> AsyncIterator[ytconvert_pb2.JobEvent]:
        req = ytconvert_pb2.WatchJobRequest(job_id=job_id, send_initial=send_initial)
        stream = self.stub.WatchJob(req, metadata=self.metadata)
        async for ev in stream:
            yield ev

    async def get_result(self, job_id: str, timeout_sec: float = 30.0) -> ytconvert_pb2.ConvertResult:
        req = ytconvert_pb2.GetResultRequest(job_id=job_id)
        return await self.stub.GetResult(req, metadata=self.metadata, timeout=timeout_sec)

    async def download_result(
        self,
        *,
        job_id: str,
        variant_id: str,
        artifact_id: str,
        offset: int = 0,
    ) -> AsyncIterator[ytconvert_pb2.DownloadChunk]:
        req = ytconvert_pb2.DownloadRequest(
            job_id=job_id,
            variant_id=variant_id,
            artifact_id=artifact_id,
            offset=offset,
        )
        stream = self.stub.DownloadResult(req, metadata=self.metadata)
        async for ch in stream:
            yield ch