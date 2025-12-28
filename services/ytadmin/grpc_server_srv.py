from __future__ import annotations
import asyncio
import logging
import grpc

from config.ytadmin.grpc_conf import load_grpc_config
from services.ytadmin.health_srv import collect_health

from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection


class AppGrpcServer:
    """
    Asynchronous gRPC application server:
    - Returns the standard grpc.health.v1.Health/Check
    - Enables reflection (grpcurl list/describe)
    - Periodically updates the SERVING/NOT_SERVING status using collect_health()
    """
    def __init__(self) -> None:
        self.cfg = load_grpc_config()
        self.server: grpc.aio.Server | None = None
        self.health_srv = health.HealthServicer()
        self._task_update: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self.server = grpc.aio.server()

        # Health service
        health_pb2_grpc.add_HealthServicer_to_server(self.health_srv, self.server)

        # Reflection
        service_names = (
            health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
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
        self._running = False
        if self._task_update:
            self._task_update.cancel()
        if self.server:
            await self.server.stop(grace=None)
            logging.info("gRPC server stopped")

    async def _loop_update_status(self) -> None:
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