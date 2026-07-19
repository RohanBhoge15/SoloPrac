"""Redis service client — cache + arq worker queue for async tasks."""

import json
import redis.asyncio as redis
from typing import Any, Optional, List, Dict
from contextlib import asynccontextmanager

from app.config import settings


class RedisService:
    def __init__(self):
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> redis.Redis:
        if self._client is not None:
            return self._client

        self._client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
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

    @asynccontextmanager
    async def transaction(self):
        """Simple transaction-like grouping."""
        client = await self.connect()
        if client:
            yield self
            # Note: Redis async client doesn't support MULTI transactions easily
            # For now, use pipeline
            yield self

    async def close(self):
        if self._client:
            await self._client.close()


# Global instance
redis_service = RedisService()