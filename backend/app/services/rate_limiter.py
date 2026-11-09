"""Fixed-window rate limiter backed by Redis."""

from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=window_seconds, nx=True)
            pipe.incr(key)
            pipe.ttl(key)
            _, count, ttl = await pipe.execute()
        return RateLimitResult(allowed=int(count) <= limit, retry_after_seconds=max(int(ttl), 1))

    async def reset(self, key: str) -> None:
        await self._redis.delete(key)
