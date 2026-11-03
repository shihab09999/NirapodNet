"""Small in-memory rate limiter for Phase 3.

This is per-process state, which fits NirapodNet's single-server
LAN deployment: one uvicorn process serves the whole local
network. It is not shared across processes, and it is not a
substitute for a reverse proxy's limits in a larger deployment.
See docs/SECURITY.md.
"""

import threading
import time


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()

        with self._lock:
            hits = self._hits.setdefault(key, [])
            hits[:] = [t for t in hits if now - t < window_seconds]

            if len(hits) >= limit:
                return False

            hits.append(now)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def reset_rate_limiter():
    limiter.reset()
