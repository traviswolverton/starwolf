import json
import os

import redis as redis_lib

_client = None


def _get_client() -> redis_lib.Redis:
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        _client = redis_lib.from_url(url, decode_responses=True)
    return _client


def cache_get(key: str):
    """Return cached value or None. Silently returns None if Redis is unavailable."""
    try:
        val = _get_client().get(key)
        return json.loads(val) if val is not None else None
    except Exception:
        return None


def cache_set(key: str, value, ttl: int) -> None:
    """Store value in cache with TTL in seconds. Silently no-ops if Redis is unavailable."""
    try:
        _get_client().setex(key, ttl, json.dumps(value))
    except Exception:
        pass
