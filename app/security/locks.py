from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.services.shop import ShopError


@asynccontextmanager
async def exclusive(redis: Redis, key: str, ttl: int = 20):
    token = await redis.set(f"lock:{key}", "1", nx=True, ex=ttl)
    if not token:
        raise ShopError("busy")
    try:
        yield
    finally:
        await redis.delete(f"lock:{key}")
