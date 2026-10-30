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


def check_db_pool() -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Checks the PostgreSQL connection pool: unhealthy when it has been fully
    busy (no free connection) for more than 60 seconds - that is what a stuck
    pool looks like from outside, while the process itself stays alive.
    Returns (ok, error_message_if_any, stats).
    """
    try:
        from db import pool_stats
        st = pool_stats()
    except Exception as e:
        return True, None, {"error": f"pool_stats:{e}"}
    if st.get("initialized") and float(st.get("exhausted_for_sec") or 0.0) > 60.0:
        return False, f"db_pool_exhausted:{int(st.get('exhausted_for_sec') or 0)}s", st
    return True, None, st


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
    ok_pool, msg_pool, pool_st = check_db_pool()

    healthy = ok_db and ok_cache and ok_pool

    status: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {
            "db": "ok" if ok_db else (msg_db or "fail"),
            "cache": "ok" if ok_cache else (msg_cache or "fail"),
            "db_pool": "ok" if ok_pool else (msg_pool or "fail"),
        },
        "metrics": {
            "uptime_sec": float(uptime.uptime_sec()),
            "uptime_started_iso": uptime.started_iso(),
            # metrics must stay flat name -> number (protobuf map<string,double>)
            "db_pool_size": float(pool_st.get("size") or 0),
            "db_pool_idle": float(pool_st.get("idle") or 0),
            "db_pool_held": float(pool_st.get("held") or 0),
            "db_pool_oldest_hold_sec": float(pool_st.get("oldest_hold_sec") or 0.0),
        },
        "healthy": healthy,
    }
    return status