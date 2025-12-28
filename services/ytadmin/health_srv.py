from __future__ import annotations
import time
from typing import Dict, Any, Tuple, Optional

from services.monitor.uptime import uptime

def check_db() -> Tuple[bool, Optional[str]]:
    """
    Performs a minimal database liveness check.
    Replace with a real query (e.g., SELECT 1) using your DB layer.
    Returns (ok, error_message_if_any).
    """
    try:
        # ex.: db.execute("SELECT 1")
        return True, None
    except Exception as e:
        return False, f"db_error:{e}"


def check_cache() -> Tuple[bool, Optional[str]]:
    """
    Performs a minimal cache liveness check.
    Replace with real Redis/Memcached ping.
    Returns (ok, error_message_if_any).
    """
    try:
        # ex.: redis.ping()
        return True, None
    except Exception as e:
        return False, f"cache_error:{e}"


def collect_health() -> Dict[str, Any]:
    """
    Collects a compact health snapshot of the application without secrets.

    Returns:
    {
      "timestamp": ISO8601 UTC string,
      "checks": { "db": "ok"|"fail:...", "cache": "ok"|"fail:..." },
      "metrics": {
        "uptime_sec": float,
        "uptime_started_iso": str,
        // add more metrics on demand
      },
      "healthy": bool
    }
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
        },
        "healthy": healthy,
    }
    return status