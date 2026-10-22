"""In-memory, per-process limiter for failed logins."""

import math
import threading
import time
from collections import deque

MAX_TRACKED_USERNAMES = 10_000


class LoginLimiter:
    def __init__(self, max_failures: int = 5, window_seconds: int = 900, clock=time.monotonic):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _prune(self, username: str, now: float) -> deque | None:
        stamps = self._failures.get(username)
        if stamps is None:
            return None
        cutoff = now - self.window_seconds
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        if not stamps:
            del self._failures[username]
            return None
        return stamps

    def retry_after(self, username: str) -> int:
        """Seconds until this username may try again; 0 if allowed now."""
        with self._lock:
            now = self._clock()
            stamps = self._prune(username, now)
            if stamps is None or len(stamps) < self.max_failures:
                return 0
            return max(1, math.ceil(stamps[0] + self.window_seconds - now))

    def record_failure(self, username: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(username, now)
            if username not in self._failures and len(self._failures) >= MAX_TRACKED_USERNAMES:
                cutoff = now - self.window_seconds
                for name in [n for n, s in self._failures.items() if s[-1] < cutoff]:
                    del self._failures[name]
            self._failures.setdefault(username, deque()).append(now)

    def reset(self, username: str) -> None:
        """Forget all failures for this username (called after a successful login)."""
        with self._lock:
            self._failures.pop(username, None)
