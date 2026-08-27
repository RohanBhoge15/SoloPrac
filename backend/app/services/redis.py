"""Redis service client — cache + arq worker queue for async tasks."""

import json
from typing import Any, Optional

import redis.asyncio as redis

from app.config import settings


class RedisService:
    def __init__(self):
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> redis.Redis:
        if self._client is not None:
            return self._client

        # Use ConnectionPool for proper connection pooling
        pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
        self._client = redis.Redis(connection_pool=pool)
        # Test connection
        await self._client.ping()
        return self._client

    async def set_cached(self, key: str, value: Any, ttl: int = 3600) -> bool:
        client = await self.connect()
        serialized = json.dumps(value, default=str)
        return await client.set(key, serialized, ex=ttl)

    async def get_cached(self, key: str) -> Optional[Any]:
        client = await self.connect()
        raw = await client.get(key)
        if not raw:
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> int:
        client = await self.connect()
        return await client.delete(key)

    async def ping(self) -> str:
        client = await self.connect()
        return await client.ping()

    async def close(self):
        try:
            if self._client:
                await self._client.close()
        except Exception:
            pass


# Global instance
redis_service = RedisService()
