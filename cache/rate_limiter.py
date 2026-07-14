# ============================================
# Redis-backed rate limiter
# Uses sliding window algorithm for smooth rate limits
# ============================================
import time
from typing import Optional
import redis.asyncio as redis


class RateLimiter:
    """
    Rate limiter using Redis sorted sets.
    
    Sliding window algorithm:
    - Store timestamps of each request in a sorted set
    - Remove old timestamps (outside the window)
    - Count remaining timestamps = current usage
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def check_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, dict]:
        """
        Check if request is allowed under rate limit.
        
        Returns:
            (allowed: bool, info: dict with details)
        """
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"
        
        # Use a pipeline for atomic operations
        async with self.redis.pipeline() as pipe:
            # Remove timestamps outside the window
            await pipe.zremrangebyscore(redis_key, 0, window_start)
            # Count remaining timestamps (current usage)
            await pipe.zcard(redis_key)
            # Add current timestamp
            await pipe.zadd(redis_key, {str(now): now})
            # Set expiration on the key (auto-cleanup)
            await pipe.expire(redis_key, window_seconds + 10)
            
            results = await pipe.execute()
        
        current_count = results[1]  # count BEFORE adding current
        
        # +1 because we already added ourselves
        total_after_this = current_count + 1
        allowed = total_after_this <= max_requests
        
        if not allowed:
            # Roll back the add if we exceeded limit
            await self.redis.zrem(redis_key, str(now))
        
        return allowed, {
            "limit": max_requests,
            "window_seconds": window_seconds,
            "current_usage": total_after_this if allowed else current_count,
            "remaining": max(0, max_requests - total_after_this) if allowed else 0,
            "reset_at": int(now + window_seconds),
        }
    
    async def reset(self, key: str) -> None:
        """Reset rate limit for a key (admin use)."""
        await self.redis.delete(f"ratelimit:{key}")
    
    async def get_current_usage(self, key: str, window_seconds: int) -> int:
        """Check current usage without incrementing."""
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"
        
        await self.redis.zremrangebyscore(redis_key, 0, window_start)
        return await self.redis.zcard(redis_key)