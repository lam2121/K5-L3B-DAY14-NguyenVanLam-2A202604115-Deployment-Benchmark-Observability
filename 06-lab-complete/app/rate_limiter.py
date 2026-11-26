"""
Rate limiting (tiêu chí 7) — sliding window 60s lưu trong Redis.
"""
import hashlib
import time
import uuid

from fastapi import HTTPException
import redis

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    if r is None:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")

    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    redis_key = f"rate_limit:{key_hash}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    try:
        r.zremrangebyscore(redis_key, 0, window_start)
        current_count = r.zcard(redis_key)
        if current_count >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        member = f"{now:.6f}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS)
        pipe.execute()
    except HTTPException:
        raise
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter storage error")
