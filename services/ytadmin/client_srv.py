from __future__ import annotations
import asyncio
import grpc
from typing import Optional, List

from config.ytadmin.ytadmin_cfg import load_config
from services.ytadmin.health_srv import collect_health
from services.ytadmin.effconf_srv import collect_effective_config

try:
    from services.ytadmin.ytadmin_proto import yurtube_pb2, yurtube_pb2_grpc  # type: ignore
except Exception:
    yurtube_pb2 = None
    yurtube_pb2_grpc = None


class YTAdminClient:
    """
    Admin ingest push client.

    Purpose:
    - Periodically push health snapshots and effective configuration to the admin service
      via ytadmin.AdminIngest (PushHealth, PushEffConf).
    - Identity fields are sourced from application config.

    Usage:
    - Controlled via env flag YTADMIN_ENABLED.
    - Call start() on app startup and stop() on shutdown.
    """

    def __init__(self):
        self.cfg = load_config()
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional["yurtube_pb2_grpc.AdminIngestStub"] = None  # type: ignore
        self._tasks: List[asyncio.Task] = []

    def _auth_metadata(self) -> List[tuple]:
        """
        Builds gRPC metadata for auth (Authorization: Bearer <token>) if configured.
        """
        md = []
        if self.cfg.token:
            md.append(("authorization", f"Bearer {self.cfg.token}"))
        return md

    async def _create_channel(self):
        """
        Creates a gRPC channel to the admin ingest service: cfg.host:cfg.port.
        Supports plaintext for now; TLS wiring can be added later if needed.
        """
        target = f"{self.cfg.host}:{self.cfg.port}"
        if self.cfg.tls_ca_path:
            with open(self.cfg.tls_ca_path, "rb") as f:
                creds = grpc.ssl_channel_credentials(root_certificates=f.read())
            self._channel = grpc.aio.secure_channel(target, creds)
        else:
            self._channel = grpc.aio.insecure_channel(target)

        self._stub = yurtube_pb2_grpc.AdminIngestStub(self._channel)  # type: ignore

    async def start(self):
        """
        Starts periodic push tasks if enabled and stubs are present.
        """
        if not self.cfg.enabled:
            return
        if yurtube_pb2 is None or yurtube_pb2_grpc is None:
            raise RuntimeError("yurtube proto not built. Generate Python stubs from yurtube.proto.")
        await self._create_channel()

        if self.cfg.push_health_interval_sec > 0:
            self._tasks.append(asyncio.create_task(self._loop_push_health()))

        if self.cfg.effconf_enable and self.cfg.push_effconf_interval_sec > 0:
            self._tasks.append(asyncio.create_task(self._loop_push_effconf()))

    async def stop(self):
        """
        Cancels periodic tasks and closes the gRPC channel.
        """
        for t in self._tasks:
            t.cancel()
        if self._channel:
            await self._channel.close()

    async def _loop_push_health(self):
        """
        Background loop to push health snapshots at configured intervals.
        """
        while True:
            try:
                await self.push_health_once()
            except Exception:
                pass
            await asyncio.sleep(self.cfg.push_health_interval_sec)

    async def _loop_push_effconf(self):
        """
        Background loop to push effective config snapshots at configured intervals.
        """
        while True:
            try:
                await self.push_effconf_once()
            except Exception:
                pass
            await asyncio.sleep(self.cfg.push_effconf_interval_sec)

    async def push_health_once(self):
        """
        Pushes a single health snapshot to the admin ingest service.
        """
        data = collect_health()
        req = yurtube_pb2.PushHealthRequest(  # type: ignore
            identity=yurtube_pb2.ServiceIdentity(  # type: ignore
                name=self.cfg.service_name,
                instance_id=self.cfg.instance_id,
                host=self.cfg.identity_host,
                version=self.cfg.version,
            ),
            healthy=bool(data.get("healthy", True)),
            checks=data.get("checks", {}),
            metrics=data.get("metrics", {}),
            ts_iso=str(data.get("timestamp", "")),
        )
        md = self._auth_metadata()
        await self._stub.PushHealth(req, metadata=md)  # type: ignore

    async def push_effconf_once(self):
        """
        Pushes a single effective configuration snapshot to the admin ingest service.
        Secrets are already redacted in `collect_effective_config`.
        """
        cfg_map, redacted_keys, cfg_hash = collect_effective_config(
            whitelist=self.cfg.effconf_whitelist,
            redact_keys=self.cfg.effconf_redact_keys,
        )
        req = yurtube_pb2.PushEffConfRequest(  # type: ignore
            identity=yurtube_pb2.ServiceIdentity(  # type: ignore
                name=self.cfg.service_name,
                instance_id=self.cfg.instance_id,
                host=self.cfg.identity_host,
                version=self.cfg.version,
            ),
            config=cfg_map,
            redacted_keys=redacted_keys,
            config_hash=cfg_hash,
        )
        md = self._auth_metadata()
        await self._stub.PushEffConf(req, metadata=md)  # type: ignore