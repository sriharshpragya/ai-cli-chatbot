# ============================================
# Session cache — cache validated API keys
# Avoid database hits on every request
# ============================================
import json
from typing import Optional
import redis.asyncio as redis


class SessionCache:
    """Cache validated API key → user data mappings."""
    
    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 300):
        self.redis = redis_client
        self.ttl = ttl_seconds  # 5 minute default cache
    
    def _key(self, api_key_hash: str) -> str:
        """Namespace the cache key."""
        return f"session:key:{api_key_hash[:16]}"
    
    async def get(self, api_key_hash: str) -> Optional[dict]:
        """Get cached user data by API key hash prefix."""
        cached = await self.redis.get(self._key(api_key_hash))
        if cached:
            return json.loads(cached)
        return None
    
    async def set(self, api_key_hash: str, user_data: dict) -> None:
        """Cache user data with expiration."""
        await self.redis.setex(
            self._key(api_key_hash),
            self.ttl,
            json.dumps(user_data),
        )
    
    async def invalidate(self, api_key_hash: str) -> None:
        """Remove from cache (e.g., when key is revoked)."""
        await self.redis.delete(self._key(api_key_hash))