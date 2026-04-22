import os
from typing import Optional

try:
    import redis.asyncio as redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


_client: Optional["redis.Redis"] = None


def get_redis() -> Optional["redis.Redis"]:
    global _client
    if _client is not None:
        return _client

    if redis is None:
        return None

    url = os.getenv("REDIS_URL")
    if not url:
        return None

    _client = redis.from_url(url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is None:
        return
    try:
        await _client.close()
    finally:
        _client = None
