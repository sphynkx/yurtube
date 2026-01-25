from __future__ import annotations

from typing import List, Optional, Tuple

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from config.ytconvert.ytconvert_cfg import load_ytconvert_config
from utils.ytconvert.ytconvert_servers_ut import YtconvertServer


async def pick_server_with_healthcheck() -> YtconvertServer:
    """
    Picks first SERVING server from YTCONVERT_SERVERS by calling grpc.health.v1.Health/Check.

    Raises RuntimeError if none are healthy.
    """
    cfg = load_ytconvert_config()
    if not cfg.servers:
        raise RuntimeError("YTCONVERT_SERVERS is empty")

    last_err = None

    for srv in cfg.servers:
        try:
            # plaintext for now (matches grpcurl -plaintext)
            async with grpc.aio.insecure_channel(srv.hostport) as ch:
                stub = health_pb2_grpc.HealthStub(ch)
                req = health_pb2.HealthCheckRequest(service="")
                resp = await stub.Check(req, timeout=2.0)
                if resp.status == health_pb2.HealthCheckResponse.SERVING:
                    return srv
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"no healthy ytconvert servers (last_err={last_err!r})")