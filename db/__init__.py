"""
PostgreSQL connection pool (asyncpg).

Public API (unchanged): init_db_pool(), get_conn(), release_conn(conn), shutdown_db_pool().
New: pool_stats() - snapshot for health checks / diagnostics.

Safety features
---------------
1. Re-entrant per task. If the current asyncio task already holds a connection,
   get_conn() returns the SAME connection (reference-counted) instead of taking a
   second one from the pool; release_conn() returns it to the pool only when the
   outermost holder releases it.
   Why: route code holds a connection and calls helpers that do their own
   get_conn() (e.g. watch_page -> fetch_rightbar_for_video -> fetch_trending).
   With a bounded pool, N concurrent requests each holding 1 connection and
   waiting for a 2nd one deadlock the whole pool forever.
   Different tasks (asyncio.gather / create_task) never share a connection.
2. Acquire timeout. Waiting for a free connection is bounded (DB_ACQUIRE_TIMEOUT_SEC),
   so any future exhaustion becomes a fast error (with a list of holders in the log)
   instead of an endless hang.
3. Command timeout (DB_COMMAND_TIMEOUT_SEC) so a stuck query cannot hold a slot forever.
4. Pool initialisation is serialised (no duplicate pools on concurrent first calls).
5. A light watchdog logs connections held for too long (diagnostic only, never kills anything).
"""
import asyncio
import logging
import os
import sys
import time
import weakref
from typing import Any, Dict, List, Optional

import asyncpg

from config.config import settings

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except Exception:
        return default


POOL_MIN_SIZE = _env_int("DB_POOL_MIN", 1)
POOL_MAX_SIZE = _env_int("DB_POOL_MAX", 10)
ACQUIRE_TIMEOUT_SEC = _env_float("DB_ACQUIRE_TIMEOUT_SEC", 15.0)
COMMAND_TIMEOUT_SEC = _env_float("DB_COMMAND_TIMEOUT_SEC", 120.0)
HOLD_WARN_SEC = _env_float("DB_HOLD_WARN_SEC", 300.0)
WATCHDOG_INTERVAL_SEC = _env_float("DB_WATCHDOG_INTERVAL_SEC", 30.0)

class DBPoolExhausted(asyncio.TimeoutError):
    """No free DB connection within DB_ACQUIRE_TIMEOUT_SEC (pool is saturated)."""


_pool: Optional[asyncpg.Pool] = None
_last_exhausted_log = 0.0
_init_lock = asyncio.Lock()
_watchdog_task: Optional[asyncio.Task] = None

# task -> [connection, ref_count, acquired_at_monotonic, "file:line:func"]
# Weak keys: a finished/collected task never pins an entry in memory.
_held: "weakref.WeakKeyDictionary[asyncio.Task, List[Any]]" = weakref.WeakKeyDictionary()

# monotonic time since when the pool has been fully busy (None = not exhausted)
_exhausted_since: Optional[float] = None


def _caller(depth: int = 2) -> str:
    try:
        f = sys._getframe(depth)
        path = f.f_code.co_filename.replace("\\", "/")
        short = path.split("/yurtube/")[-1] if "/yurtube/" in path else path.rsplit("/", 1)[-1]
        return f"{short}:{f.f_lineno}:{f.f_code.co_name}"
    except Exception:
        return "?"


def _current_task() -> Optional["asyncio.Task"]:
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


def _holders_report(limit: int = 15) -> str:
    now = time.monotonic()
    rows = []
    try:
        for entry in list(_held.values()):
            rows.append(f"{entry[3]} age={now - entry[2]:.0f}s refs={entry[1]}")
    except Exception:
        pass
    rows.sort()
    return "; ".join(rows[:limit]) if rows else "(none tracked)"


async def init_db_pool() -> asyncpg.Pool:
    global _pool, _watchdog_task
    if _pool is not None:
        return _pool
    async with _init_lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=POOL_MIN_SIZE,
                max_size=POOL_MAX_SIZE,
                command_timeout=COMMAND_TIMEOUT_SEC,
            )
            logger.info(
                "PostgreSQL pool initialized (max=%s acquire_timeout=%ss command_timeout=%ss)",
                POOL_MAX_SIZE, ACQUIRE_TIMEOUT_SEC, COMMAND_TIMEOUT_SEC,
            )
            if _watchdog_task is None or _watchdog_task.done():
                _watchdog_task = asyncio.get_running_loop().create_task(_watchdog_loop())
    assert _pool is not None
    return _pool


async def get_conn() -> asyncpg.Connection:
    pool = _pool if _pool is not None else await init_db_pool()

    task = _current_task()
    if task is not None:
        entry = _held.get(task)
        if entry is not None:
            held = entry[0]
            if getattr(held, "_con", True) is None:
                # Stale entry: the connection was released from another task. Drop it.
                try:
                    del _held[task]
                except KeyError:
                    pass
            else:
                # Re-entrant: this task already holds a connection - reuse it.
                entry[1] += 1
                return held

    try:
        conn = await pool.acquire(timeout=ACQUIRE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        global _last_exhausted_log
        now = time.monotonic()
        if now - _last_exhausted_log >= 10.0:
            # Full report at most once per 10s, so a burst does not flood the log.
            _last_exhausted_log = now
            logger.error(
                "DB pool exhausted: no free connection within %.0fs (size=%s idle=%s). Holders: %s | waiter: %s",
                ACQUIRE_TIMEOUT_SEC, pool.get_size(), pool.get_idle_size(), _holders_report(), _caller(),
            )
        raise DBPoolExhausted("no free DB connection within %.0fs" % ACQUIRE_TIMEOUT_SEC) from None

    if task is not None:
        _held[task] = [conn, 1, time.monotonic(), _caller()]
    return conn


async def release_conn(conn: asyncpg.Connection) -> None:
    global _pool
    if conn is None:
        return

    # Re-entrant release: only the outermost release really returns the connection.
    task = _current_task()
    if task is not None:
        entry = _held.get(task)
        if entry is not None and entry[0] is conn:
            entry[1] -= 1
            if entry[1] > 0:
                return
            try:
                del _held[task]
            except KeyError:
                pass

    try:
        if _pool is not None:
            await _pool.release(conn)
        else:
            await conn.close()
    except Exception as e:
        try:
            await conn.close()
        except Exception:
            pass
        logger.warning("release_conn: safe-closed connection due to error: %s", e)


def pool_stats() -> Dict[str, Any]:
    """Cheap, synchronous snapshot for health checks."""
    if _pool is None:
        return {"initialized": False}
    now = time.monotonic()
    oldest = 0.0
    try:
        for entry in list(_held.values()):
            oldest = max(oldest, now - entry[2])
    except Exception:
        pass
    size = _pool.get_size()
    idle = _pool.get_idle_size()
    return {
        "initialized": True,
        "size": size,
        "max": POOL_MAX_SIZE,
        "idle": idle,
        "held": len(_held),
        "oldest_hold_sec": round(oldest, 1),
        "exhausted_for_sec": round(now - _exhausted_since, 1) if _exhausted_since is not None else 0.0,
    }


async def _watchdog_loop() -> None:
    """Diagnostics only: tracks pool exhaustion and logs long-held connections."""
    global _exhausted_since
    while True:
        try:
            await asyncio.sleep(WATCHDOG_INTERVAL_SEC)
            pool = _pool
            if pool is None:
                return
            now = time.monotonic()
            busy = pool.get_size() >= POOL_MAX_SIZE and pool.get_idle_size() == 0
            if busy:
                if _exhausted_since is None:
                    _exhausted_since = now
            else:
                _exhausted_since = None
            for entry in list(_held.values()):
                age = now - entry[2]
                if age > HOLD_WARN_SEC:
                    logger.warning("DB connection held for %.0fs by %s (refs=%s)", age, entry[3], entry[1])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("db watchdog error: %s", e)


async def shutdown_db_pool() -> None:
    global _pool, _watchdog_task
    if _watchdog_task is not None:
        _watchdog_task.cancel()
        _watchdog_task = None
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")