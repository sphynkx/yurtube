from __future__ import annotations
import asyncio
import logging
import os
import grpc

from config.ytadmin.grpc_conf import load_grpc_config
from config.ytadmin.ytadmin_cfg import load_config
from services.ytadmin.health_srv import collect_health
from services.monitor.uptime import uptime

# Standard gRPC Health-Check service (grpcio-health-checking)
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# Server Reflection for grpcurl (list/describe)
from grpc_reflection.v1alpha import reflection

try:
    from services.ytadmin.ytadmin_proto import info_pb2, info_pb2_grpc  # type: ignore
    HAVE_INFO = True
except Exception as e:
    info_pb2 = None
    info_pb2_grpc = None
    HAVE_INFO = False
    logging.warning("info proto stubs not found: %s", e)


if HAVE_INFO:
    class InfoServicer(info_pb2_grpc.InfoServicer):  # type: ignore
        """
        Unified info service for pull monitoring (grpc.health.v1.Info).

        Purpose:
        - Provide a single RPC (All) that returns key identity and runtime metadata
          so the admin service can fetch everything via grpcurl without local proto files.

        Data source:
        - Values come from application config (config/ytadmin/ytadmin_cfg.py) and runtime state (uptime).
        """

        def __init__(self) -> None:
            # Application config for identity fields
            self.app_cfg = load_config()

        async def All(self, request, context):
            """
            Returns InfoResponse with identity and runtime fields:

            - app_name: human-readable application name (e.g., "YurTube")
            - instance_id: unique instance identifier
            - host: public address of this application (e.g., "127.0.0.1:50051")
            - version: application version
            - uptime: seconds as a string
            - labels: optional key-value labels (e.g., environment)
            - metrics: optional numerical metrics (e.g., uptime_sec)
            """
            # Compute uptime once
            up_sec = float(uptime.uptime_sec())

            # Optional environment label (empty string filtered client-side if needed)
            env = os.getenv("APP_ENV") or os.getenv("ENV") or ""

            return info_pb2.InfoResponse(  # type: ignore
                app_name=self.app_cfg.service_name,
                instance_id=self.app_cfg.instance_id,
                host=self.app_cfg.identity_host,
                version=self.app_cfg.version,
                uptime=str(int(up_sec)),
                labels={"env": env} if env else {},
                metrics={
                    "uptime_sec": up_sec,
                    # Add more metrics when available, e.g. "cpu": cpu_usage, "latency_ms": latency
                },
            )
else:
    InfoServicer = None  # Stubs missing; server will start with Health only and log a warning.


class AppGrpcServer:
    """
    Async gRPC server for the application (pull monitoring).

    Exposed services:
    - grpc.health.v1.Health/Check: basic availability status (SERVING/NOT_SERVING).
    - grpc.health.v1.Info/All: unified identity and runtime metadata for admin pulls (registered only if stubs exist).

    Notes:
    - Server Reflection is enabled for convenient grpcurl diagnostics:
      - grpcurl -plaintext 127.0.0.1:50051 list
      - grpcurl -plaintext 127.0.0.1:50051 describe grpc.health.v1.Health
      - grpcurl -plaintext 127.0.0.1:50051 describe grpc.health.v1.Info  (visible after stubs are generated)
    - Periodically updates Health status based on collect_health().
    """

    def __init__(self) -> None:
        # gRPC server config (host/port)
        self.cfg = load_grpc_config()

        # gRPC aio server instance
        self.server: grpc.aio.Server | None = None

        # Standard HealthServicer (grpcio-health-checking)
        self.health_srv = health.HealthServicer()

        # Background task for periodic status updates
        self._task_update: asyncio.Task | None = None

        # Server running flag
        self._running = False

    async def start(self) -> None:
        """
        Initialize and start the gRPC server:
        - Register HealthServicer and InfoServicer (if available).
        - Enable Server Reflection.
        - Begin listening on cfg.host:cfg.port.
        - Launch the background task that updates Health status.
        """
        if self._running:
            return

        # Create aio server
        self.server = grpc.aio.server()

        # Register standard Health service
        health_pb2_grpc.add_HealthServicer_to_server(self.health_srv, self.server)

        # Register our Info service if stubs are present
        if InfoServicer is not None and info_pb2_grpc is not None:
            info_pb2_grpc.add_InfoServicer_to_server(InfoServicer(), self.server)
        else:
            logging.warning(
                "Info service not registered: missing stubs (services/ytadmin_proto/info.proto). "
                "Generate stubs to enable grpc.health.v1.Info/All."
            )

        # Build Reflection list
        service_names = [
            health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,    # "grpc.health.v1.Health"
            reflection.SERVICE_NAME,
        ]
        if info_pb2 is not None and "Info" in info_pb2.DESCRIPTOR.services_by_name:
            service_names.insert(1, info_pb2.DESCRIPTOR.services_by_name["Info"].full_name)  # type: ignore

        # Enable Reflection
        reflection.enable_server_reflection(tuple(service_names), self.server)

        # gRPC server address (plaintext for initial phase)
        addr = f"{self.cfg.host}:{self.cfg.port}"
        if self.cfg.tls_enabled:
            # Add secure_channel_credentials and add_secure_port when TLS is required
            raise NotImplementedError("TLS wiring not configured yet")
        else:
            self.server.add_insecure_port(addr)

        # Start gRPC server
        await self.server.start()
        logging.info("gRPC server started on %s", addr)
        self._running = True

        # Initial Health state — NOT_SERVING until the first check
        self.health_srv.set("", health_pb2.HealthCheckResponse.NOT_SERVING)

        # Start background status updater
        self._task_update = asyncio.create_task(self._loop_update_status())

    async def stop(self) -> None:
        """
        Stop the background task and gracefully shut down the gRPC server.
        """
        self._running = False

        # Cancel background status updater
        if self._task_update:
            self._task_update.cancel()

        # Stop gRPC server
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
                # Collect local application health
                data = collect_health()
                is_ok = bool(data.get("healthy", True))

                # Map flag to Health status
                status = (
                    health_pb2.HealthCheckResponse.SERVING
                    if is_ok
                    else health_pb2.HealthCheckResponse.NOT_SERVING
                )

                # Set overall service status (service="")
                self.health_srv.set("", status)

            except Exception as e:
                # Any error -> NOT_SERVING; log and continue
                self.health_srv.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
                logging.warning("health update failed: %s", e)

            # Update interval
            await asyncio.sleep(10)


app_grpc_server = AppGrpcServer()