"""Shared analysis budget for the camera fleet.

Every camera already refuses to run the face pipeline faster than its local
`CAMERA_ANALYZE_INTERVAL_SEC` and skips idle scenes entirely. On top of that,
a corporate site with dozens of cameras can still peg the CPU if several very
busy cameras detect at once. `AnalysisScheduler` fixes that with two levers:

- a *global token bucket*: across all cameras the expensive pipeline runs at
  most `CAMERA_GLOBAL_ANALYZE_FPS` times per second (the hard ceiling);
- a *bounded thread pool*: the detections that DO run are parallelised across
  `CAMERA_ANALYSIS_POOL_SIZE` threads, so busy cameras overlap instead of
  serialising on the GIL.

Forced re-analysis (a still gate camera hitting its max-gap timer) bypasses the
bucket — it is already self-limiting to one run per camera per gap, so it can
never flood the pool.
"""

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from app.config import config


class AnalysisScheduler:
    def __init__(self):
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, config.CAMERA_ANALYSIS_POOL_SIZE),
            thread_name_prefix="cam-analysis",
        )
        self._bucket: float = float(config.CAMERA_GLOBAL_ANALYZE_FPS)
        self._last_refill = time.time()
        self._lock = threading.Lock()

    @property
    def _capacity(self) -> float:
        return max(1.0, config.CAMERA_GLOBAL_ANALYZE_FPS)

    def _refill(self):
        now = time.time()
        self._bucket = min(self._capacity, self._bucket + self._capacity * (now - self._last_refill))
        self._last_refill = now

    def try_acquire(self) -> bool:
        """Consume one global analysis slot if it is available."""
        with self._lock:
            self._refill()
            if self._bucket >= 1.0:
                self._bucket -= 1.0
                return True
            return False

    def available(self) -> float:
        with self._lock:
            self._refill()
            return round(self._bucket, 2)

    def run(self, fn: Callable):
        """Submit `fn` to the bounded pool. Caller owns the returned future."""
        return self._pool.submit(fn)

    def queue_depth(self) -> int:
        pending = self._pool._work_queue.qsize()  # bound to this scheduler
        return pending


analysis_scheduler = AnalysisScheduler()