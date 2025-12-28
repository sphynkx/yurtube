from __future__ import annotations
import time
import threading
from typing import Optional

class _Uptime:
    """
    Process uptime tracking:
    - Uses time.monotonic() for reliable duration measurement (independent of system clock changes).
    - Also stores a real-time "start" stamp (time.time()) to display the startup time.
    """
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started_monotonic: Optional[float] = None
        self._started_wall_epoch: Optional[float] = None

    def set_started(self) -> None:
        """Mark the process as running if not already marked."""
        with self._lock:
            if self._started_monotonic is None:
                self._started_monotonic = time.monotonic()
                self._started_wall_epoch = time.time()

    def reset(self) -> None:
        """Flush state."""
        with self._lock:
            self._started_monotonic = None
            self._started_wall_epoch = None

    def uptime_sec(self) -> float:
        """Current upime in sec."""
        with self._lock:
            if self._started_monotonic is None:
                return 0.0
            return max(0.0, time.monotonic() - self._started_monotonic)

    def started_epoch(self) -> Optional[float]:
        """Unix-epoch of start time."""
        with self._lock:
            return self._started_wall_epoch

    def started_iso(self) -> str:
        """ISO8601-line of start time (or empty)."""
        with self._lock:
            if self._started_wall_epoch is None:
                return ""
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._started_wall_epoch))


uptime = _Uptime()