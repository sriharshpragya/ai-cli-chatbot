# ============================================
# Redis client - optional (only for API mode)
# ============================================
import redis.asyncio as redis
from config import REDIS_URL, REDIS_ENABLED

redis_client = None

if REDIS_ENABLED:
    redis_client = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )


async def get_redis():
    """Dependency for FastAPI endpoints that need Redis."""
    if not REDIS_ENABLED:
        raise RuntimeError(
            "Redis not configured. Set REDIS_URL to enable API mode."
        )
    return redis_client
