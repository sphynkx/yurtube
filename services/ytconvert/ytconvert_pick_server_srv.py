from __future__ import annotations

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from config.ytconvert.ytconvert_cfg import load_ytconvert_config
from utils.ytconvert.ytconvert_servers_ut import YtconvertServer


async def pick_server_with_healthcheck() -> YtconvertServer:
    """
    Pick first ytconvert server that responds SERVING to grpc.health.v1.Health/Check.
    Tries servers in the order specified in YTCONVERT_SERVERS.
    """
    cfg = load_ytconvert_config()
    if not cfg.servers:
        raise RuntimeError("YTCONVERT_SERVERS is empty")

    last_err = None
    for srv in cfg.servers:
        try:
            async with grpc.aio.insecure_channel(srv.hostport) as ch:
                stub = health_pb2_grpc.HealthStub(ch)
                resp = await stub.Check(health_pb2.HealthCheckRequest(service=""), timeout=2.0)
                if resp.status == health_pb2.HealthCheckResponse.SERVING:
                    return srv
        except Exception as e:
            last_err = e

    raise RuntimeError(f"no healthy ytconvert servers (last_err={last_err!r})")