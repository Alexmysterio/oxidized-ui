from __future__ import annotations

import re
import threading
import time
from collections import deque

RULES: tuple[tuple[re.Pattern[str], int, int], ...] = (
    (re.compile(r"^/api/compliance/report(?:/|$)"), 20, 60),
    (re.compile(r"^/api/nodes/[^/]+/(?:test-connection|ping|trust-host-key|status|facts/collect)$"), 30, 60),
    (re.compile(r"^/api/nodes/compare$"), 30, 60),
    (re.compile(r"^/api/reconciliation(?:/|$)"), 20, 60),
    (re.compile(r"^/api/search(?:/|$)"), 60, 60),
    (re.compile(r"^/api/versions"), 60, 60),
    (re.compile(r"^/api/system/export/verify$"), 10, 60),
)

_lock = threading.Lock()
_buckets: dict[tuple[int, str], deque[float]] = {}


def check_rate_limit(path: str, client: str) -> int | None:
    """Return Retry-After seconds when the client exceeded a rule."""
    match = next(((index, rule) for index, rule in enumerate(RULES) if rule[0].search(path)), None)
    if match is None:
        return None
    index, (_pattern, limit, window) = match
    now = time.monotonic()
    with _lock:
        bucket = _buckets.setdefault((index, client), deque())
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            return max(1, int(window - (now - bucket[0])) + 1)
        bucket.append(now)
        if len(_buckets) > 10_000:
            _buckets.clear()
    return None
