from __future__ import annotations
import time
import threading
from typing import Optional


class _Uptime:
    """
    Process uptime tracker.

    Why monotonic:
    - Uses time.monotonic() for robust duration measurement (immune to system clock changes).
    - Also stores a wall-clock start timestamp (time.time()) for display (ISO8601).

    Methods:
    - set_started(): mark process start if not already set.
    - reset(): clear state (rarely needed in prod).
    - uptime_sec(): current uptime in seconds (0 if not started).
    - started_epoch(): Unix epoch of start time or None.
    - started_iso(): ISO8601 UTC string of start time or empty string.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started_monotonic: Optional[float] = None
        self._started_wall_epoch: Optional[float] = None

    def set_started(self) -> None:
        """
        Mark the process as started. No-op if already set.
        """
        with self._lock:
            if self._started_monotonic is None:
                self._started_monotonic = time.monotonic()
                self._started_wall_epoch = time.time()

    def reset(self) -> None:
        """
        Reset state to initial (not usually required in production).
        """
        with self._lock:
            self._started_monotonic = None
            self._started_wall_epoch = None

    def uptime_sec(self) -> float:
        """
        Returns current uptime in seconds. 0.0 if not started.
        """
        with self._lock:
            if self._started_monotonic is None:
                return 0.0
            return max(0.0, time.monotonic() - self._started_monotonic)

    def started_epoch(self) -> Optional[float]:
        """
        Returns Unix epoch (time.time) timestamp of start or None.
        """
        with self._lock:
            return self._started_wall_epoch

    def started_iso(self) -> str:
        """
        Returns ISO8601 UTC string of the start time or empty string if unknown.
        """
        with self._lock:
            if self._started_wall_epoch is None:
                return ""
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._started_wall_epoch))

uptime = _Uptime()