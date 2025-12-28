from __future__ import annotations
import time
from typing import Dict, Any, Tuple, Optional
from services.monitor.uptime import uptime

# TODO: implement some real checks
def check_db() -> Tuple[bool, Optional[str]]:
    try:
        # ex.: db.execute("SELECT 1")
        return True, None
    except Exception as e:
        return False, f"db_error:{e}"


def check_cache() -> Tuple[bool, Optional[str]]:
    try:
        # ex.: redis.ping()
        return True, None
    except Exception as e:
        return False, f"cache_error:{e}"


def collect_health() -> Dict[str, Any]:
    """
    Returns a compact set of metrics/flags without secrets.
    checks: {'db': 'ok'|'fail:...','cache':...}
    metrics: { 'uptime_sec': float, ... }
    """
    ok_db, msg_db = check_db()
    ok_cache, msg_cache = check_cache()

    healthy = ok_db and ok_cache

    status: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {
            "db": "ok" if ok_db else (msg_db or "fail"),
            "cache": "ok" if ok_cache else (msg_cache or "fail"),
        },
        "metrics": {
            "uptime_sec": float(uptime.uptime_sec()),
            "uptime_started_iso": uptime.started_iso(),
            "queue_depth": float(0),
        },
        "healthy": healthy,
    }
    return status