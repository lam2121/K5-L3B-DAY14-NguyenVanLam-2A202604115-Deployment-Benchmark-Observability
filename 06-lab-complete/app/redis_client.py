"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import redis

from app.config import settings


def _create_client() -> redis.Redis | None:
    if not settings.redis_url:
        return None
    try:
        return redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
    except Exception:
        return None


r: redis.Redis | None = _create_client()


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho readiness probe (/ready)."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
