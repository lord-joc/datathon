"""Per-client request limits for the public API (master prompt §8, NF18).

The client is identified by a short hash of its IP with a random salt that rotates every
24 hours, so no IP address is stored or logged. Each client has a token bucket per rule:
`per_minute` tokens are refilled every minute up to `burst`. One page of the guide makes
several calls at once (profiles, districts, live counter), so the burst lets a normal visit
through while a script that keeps calling is held to the per-minute rate.

State is in memory, because the API runs as one process on one server. A restart resets
the counters, which only ever errs on the side of the visitor.
"""

import hashlib
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

SALT_TTL_SECONDS = 24 * 3600
_MAX_CLIENTS = 50_000


@dataclass(frozen=True)
class Rule:
    name: str
    per_minute: int
    burst: int


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._salt = secrets.token_bytes(16)
        self._salt_since = clock()

    def client_key(self, address: str) -> str:
        with self._lock:
            self._rotate_salt()
            salt = self._salt
        return hashlib.sha256(salt + address.encode()).hexdigest()[:16]

    def check(self, key: str, rule: Rule) -> float | None:
        """Take one token. Returns None when allowed, else seconds until the next token."""
        now = self._clock()
        rate = rule.per_minute / 60.0
        with self._lock:
            if len(self._buckets) > _MAX_CLIENTS:
                self._buckets.clear()
            bucket = self._buckets.get((rule.name, key))
            if bucket is None:
                bucket = self._buckets[(rule.name, key)] = _Bucket(float(rule.burst), now)
            bucket.tokens = min(rule.burst, bucket.tokens + (now - bucket.updated) * rate)
            bucket.updated = now
            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return None
            return (1 - bucket.tokens) / rate

    def _rotate_salt(self) -> None:
        if self._clock() - self._salt_since >= SALT_TTL_SECONDS:
            self._salt = secrets.token_bytes(16)
            self._salt_since = self._clock()
            # Old keys can never match again, so their buckets are dropped too.
            self._buckets.clear()


def retry_after_header(seconds: float) -> str:
    return str(max(1, math.ceil(seconds)))
