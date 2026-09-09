from __future__ import annotations

import time
from collections import defaultdict, deque


class LocalRateLimiter:
    """In-process token window. No Redis roundtrip on every click."""

    def __init__(self, window_sec: float = 1.0) -> None:
        self.window_sec = window_sec
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup = time.monotonic()

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        if now - self._last_cleanup > 30:
            self._cleanup(now)
        bucket = self._hits[key]
        cutoff = now - self.window_sec
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def _cleanup(self, now: float) -> None:
        self._last_cleanup = now
        cutoff = now - self.window_sec
        dead = [k for k, q in self._hits.items() if not q or q[-1] < cutoff]
        for k in dead:
            self._hits.pop(k, None)


class TtlCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        item = self._data.get(key)
        if item is None:
            return None
        exp, value = item
        if exp < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: object, ttl: float) -> None:
        self._data[key] = (time.monotonic() + ttl, value)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


limiter = LocalRateLimiter()
cache = TtlCache()
