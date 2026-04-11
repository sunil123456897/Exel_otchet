"""Simple in-process metrics counters for monitoring consolidation runs."""

import logging
import threading
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)


class Metrics:
    """Thread-safe counters for tracking consolidation pipeline metrics.

    Usage:
        metrics = Metrics()
        metrics.increment("rows_processed", 100)
        metrics.increment("files_read")
        metrics.set_gauge("active_threads", 3)
        metrics.log_summary()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._timers: Dict[str, float] = {}
        self._start_time: float = time.monotonic()

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a counter by the given amount."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge to a specific value."""
        with self._lock:
            self._gauges[name] = value

    def start_timer(self, name: str) -> None:
        """Start a named timer."""
        with self._lock:
            self._timers[name] = time.monotonic()

    def stop_timer(self, name: str) -> float:
        """Stop a named timer and return elapsed seconds."""
        with self._lock:
            start = self._timers.pop(name, None)
            if start is None:
                return 0.0
            elapsed = time.monotonic() - start
            self._gauges[f"{name}_elapsed_s"] = elapsed
            return elapsed

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a snapshot of all metrics."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "uptime_s": round(time.monotonic() - self._start_time, 2),
            }

    def log_summary(self) -> None:
        """Log current metrics as a structured summary."""
        snap = self.get_snapshot()
        logger.info(
            f"[METRICS] counters={snap['counters']} "
            f"gauges={snap['gauges']} "
            f"uptime={snap['uptime_s']}s"
        )

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()
            self._start_time = time.monotonic()
