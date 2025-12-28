from __future__ import annotations
import asyncio
import logging
import grpc

from config.ytadmin.grpc_conf import load_grpc_config
from config.ytadmin.ytadmin_cfg import load_config
from services.ytadmin.health_srv import collect_health

from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from grpc_reflection.v1alpha import reflection

try:
    from services.ytadmin.ytadmin_proto import yurtube_pb2, yurtube_pb2_grpc  # type: ignore
except Exception as e:
    yurtube_pb2 = None
    yurtube_pb2_grpc = None
    logging.warning("yurtube proto stubs not found: %s", e)


class AppProbeServicer(yurtube_pb2_grpc.AppProbeServicer):  # type: ignore
    """
    Minimal pull-side application service (ytadmin.AppProbe).

    Purpose:
    - Provide the admin service with application identity
      (name, unique instance, host address, version) via RPC GetIdentity.
    - Complements the standard Health/Check and lets the admin UI
      display the application name ("YurTube") alongside current status.

    Data source:
    - Values come from the application configs (config/ytadmin/ytadmin_cfg.py).
    """

    def __init__(self) -> None:
        self.app_cfg = load_config()

    async def GetIdentity(self, request, context):
        """
        Return application ServiceIdentity:
        - name: "YurTube" (or the value from SERVICE_NAME)
        - instance_id: unique instance identifier
        - host: public address of the application itself (e.g. "127.0.0.1:50051")
        - version: application version string
        """
        return yurtube_pb2.ServiceIdentity(  # type: ignore
            name=self.app_cfg.service_name,
            instance_id=self.app_cfg.instance_id,
            host=self.app_cfg.identity_host,
            version=self.app_cfg.version,
        )


class AppGrpcServer:
    """
    Async gRPC server for the application (pull monitoring).

    Exposed services:
    - grpc.health.v1.Health/Check: basic availability status (SERVING/NOT_SERVING).
    - ytadmin.AppProbe/GetIdentity: application identity (name, instance, host, version).

    Notes:
    - Server Reflection is enabled for convenient grpcurl diagnostics:
      - grpcurl -plaintext 127.0.0.1:50051 list
      - grpcurl -plaintext 127.0.0.1:50051 describe grpc.health.v1.Health
      - grpcurl -plaintext 127.0.0.1:50051 describe ytadmin.AppProbe
    - Periodically updates Health status based on collect_health().
    """

    def __init__(self) -> None:
        self.cfg = load_grpc_config()

        self.server: grpc.aio.Server | None = None

        self.health_srv = health.HealthServicer()

        self._task_update: asyncio.Task | None = None

        self._running = False

    async def start(self) -> None:
        """
        Initialize and start the gRPC server:
        - Register HealthServicer and AppProbeServicer.
        - Enable Server Reflection.
        - Begin listening on cfg.host:cfg.port.
        - Launch the background task that updates Health status.
        """
        if self._running:
            return

        if yurtube_pb2 is None or yurtube_pb2_grpc is None:
            raise RuntimeError(
                "yurtube proto not built. Generate stubs from services/ytadmin/ytadmin_proto/yurtube.proto"
            )

        self.server = grpc.aio.server()

        health_pb2_grpc.add_HealthServicer_to_server(self.health_srv, self.server)

        yurtube_pb2_grpc.add_AppProbeServicer_to_server(AppProbeServicer(), self.server)

        # Enable Reflection (Health + AppProbe + Reflection)
        service_names = (
            health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
            yurtube_pb2.DESCRIPTOR.services_by_name["AppProbe"].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(service_names, self.server)

        addr = f"{self.cfg.host}:{self.cfg.port}"
        if self.cfg.tls_enabled:
            raise NotImplementedError("TLS wiring not configured yet")
        else:
            self.server.add_insecure_port(addr)

        await self.server.start()
        logging.info("gRPC server started on %s", addr)
        self._running = True

        self.health_srv.set("", health_pb2.HealthCheckResponse.NOT_SERVING)

        self._task_update = asyncio.create_task(self._loop_update_status())

    async def stop(self) -> None:
        """
        Stop the background task and gracefully shut down the gRPC server.
        """
        self._running = False

        if self._task_update:
            self._task_update.cancel()

        if self.server:
            await self.server.stop(grace=None)
            logging.info("gRPC server stopped")

    async def _loop_update_status(self) -> None:
        """
        Every 10 seconds:
        - Compute application health via collect_health()
        - Set the corresponding Health status (SERVING/NOT_SERVING)

        Notes:
        - Empty string "" is used as the "overall" service-name per the Health standard.
        - Any error is treated as NOT_SERVING and logged.
        """
        while self._running:
            try:
                data = collect_health()
                is_ok = bool(data.get("healthy", True))

                status = (
                    health_pb2.HealthCheckResponse.SERVING
                    if is_ok
                    else health_pb2.HealthCheckResponse.NOT_SERVING
                )

                self.health_srv.set("", status)

            except Exception as e:
                self.health_srv.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
                logging.warning("health update failed: %s", e)

            await asyncio.sleep(10)


app_grpc_server = AppGrpcServer()