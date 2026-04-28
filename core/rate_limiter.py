from __future__ import annotations

import threading
from collections import defaultdict, deque
from time import time

from core.config import settings


class AuthorRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, author_id: str) -> tuple[bool, int]:
        limit = max(0, settings.LLM_RATE_LIMIT_REQUESTS)
        window_seconds = max(1, settings.LLM_RATE_LIMIT_WINDOW_SECONDS)

        if limit == 0:
            return True, 0

        now = time()
        window_start = now - window_seconds

        with self._lock:
            timestamps = self._requests[author_id]
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= limit:
                retry_after = max(1, int(timestamps[0] + window_seconds - now))
                return False, retry_after

            timestamps.append(now)
            return True, 0


author_rate_limiter = AuthorRateLimiter()
