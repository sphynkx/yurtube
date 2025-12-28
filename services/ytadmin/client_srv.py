from __future__ import annotations
import asyncio
import grpc
from typing import Optional, List

from config.ytadmin.ytadmin_cfg import load_config
from service.ytadmin.health_srv import collect_health
from service.ytadmin.effconf_srv import collect_effective_config

try:
    from service.ytadmin.ytadmin_proto import ytadmin_pb2, ytadmin_pb2_grpc  # type: ignore
except Exception:
    ytadmin_pb2 = None
    ytadmin_pb2_grpc = None


class YTAdminClient:
    def __init__(self):
        self.cfg = load_config()
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional["ytadmin_pb2_grpc.AdminIngestStub"] = None  # type: ignore
        self._tasks: List[asyncio.Task] = []

    def _auth_metadata(self) -> List[tuple]:
        md = []
        if self.cfg.token:
            md.append(("authorization", f"Bearer {self.cfg.token}"))
        return md

    async def _create_channel(self):
        target = f"{self.cfg.host}:{self.cfg.port}"
        if self.cfg.tls_ca_path:
            with open(self.cfg.tls_ca_path, "rb") as f:
                creds = grpc.ssl_channel_credentials(root_certificates=f.read())
            self._channel = grpc.aio.secure_channel(target, creds)
        else:
            self._channel = grpc.aio.insecure_channel(target)

        self._stub = ytadmin_pb2_grpc.AdminIngestStub(self._channel)  # type: ignore

    async def start(self):
        if not self.cfg.enabled:
            return
        if ytadmin_pb2 is None or ytadmin_pb2_grpc is None:
            raise RuntimeError("ytadmin proto not built. Ensure Python stubs are generated for ytadmin.proto.")
        await self._create_channel()

        # Periodically send health
        if self.cfg.push_health_interval_sec > 0:
            self._tasks.append(asyncio.create_task(self._loop_push_health()))

        # Periodically send effective config
        if self.cfg.effconf_enable and self.cfg.push_effconf_interval_sec > 0:
            self._tasks.append(asyncio.create_task(self._loop_push_effconf()))

    async def stop(self):
        for t in self._tasks:
            t.cancel()
        if self._channel:
            await self._channel.close()

    async def _loop_push_health(self):
        while True:
            try:
                await self.push_health_once()
            except Exception:
                # TODO: connect logger here
                pass
            await asyncio.sleep(self.cfg.push_health_interval_sec)

    async def _loop_push_effconf(self):
        while True:
            try:
                await self.push_effconf_once()
            except Exception:
                pass
            await asyncio.sleep(self.cfg.push_effconf_interval_sec)

    async def push_health_once(self):
        data = collect_health()
        req = ytadmin_pb2.PushHealthRequest(  # type: ignore
            identity=ytadmin_pb2.ServiceIdentity(  # type: ignore
                name=self.cfg.service_name,
                instance_id=self.cfg.instance_id,
                host=self.cfg.host,
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
        cfg_map, redacted_keys, cfg_hash = collect_effective_config(
            whitelist=self.cfg.effconf_whitelist,
            redact_keys=self.cfg.effconf_redact_keys,
        )
        req = ytadmin_pb2.PushEffConfRequest(  # type: ignore
            identity=ytadmin_pb2.ServiceIdentity(  # type: ignore
                name=self.cfg.service_name,
                instance_id=self.cfg.instance_id,
                host=self.cfg.host,
                version=self.cfg.version,
            ),
            config=cfg_map,
            redacted_keys=redacted_keys,
            config_hash=cfg_hash,
        )
        md = self._auth_metadata()
        await self._stub.PushEffConf(req, metadata=md)  # type: ignore


