"""The in-memory token bucket: the reference limiter every other limiter must agree with.

Balances and times are exact fractions, so a reservation equal to the balance is allowed and the
wait is rounded up from an exact value even when the refill rate is not a whole number (100 tokens
per minute is 5/3 per second). The clock is read once per call, inside the lock.

Known limits: buckets are never evicted (their number is bounded by the number of configured API
keys), and the lock only matters if a future change adds an await inside the critical section,
because asyncio never switches tasks between awaits.
"""

import asyncio
import math
from dataclasses import dataclass
from fractions import Fraction

from app.clock import Clock
from app.limits.limiter import Decision

SECONDS_PER_MINUTE = 60


@dataclass(slots=True)
class _Bucket:
    balance_tokens: Fraction
    updated_seconds: Fraction


class InMemoryRateLimiter:
    def __init__(self, clock: Clock, tokens_per_minute: int, capacity_tokens: int) -> None:
        if tokens_per_minute <= 0:
            raise ValueError("tokens_per_minute must be greater than zero")
        if capacity_tokens <= 0:
            raise ValueError("capacity_tokens must be greater than zero")
        self._clock = clock
        self._capacity_tokens = capacity_tokens
        self._refill_tokens_per_second = Fraction(tokens_per_minute, SECONDS_PER_MINUTE)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, key: str, estimated_tokens: int) -> Decision:
        if estimated_tokens < 0:
            raise ValueError("estimated_tokens must not be negative")
        async with self._lock:
            bucket = self._refilled_bucket(key, Fraction(self._clock.now_seconds()))
            if estimated_tokens > self._capacity_tokens:
                # Waiting can never help, so there is no retry hint.
                return self._decision(bucket, allowed=False, retry_after_seconds=None)
            if bucket.balance_tokens >= estimated_tokens:
                bucket.balance_tokens -= estimated_tokens
                return self._decision(bucket, allowed=True, retry_after_seconds=None)
            wait_seconds = (
                estimated_tokens - bucket.balance_tokens
            ) / self._refill_tokens_per_second
            return self._decision(
                bucket, allowed=False, retry_after_seconds=math.ceil(wait_seconds)
            )

    async def settle(self, key: str, reserved_tokens: int, actual_tokens: int) -> None:
        if reserved_tokens < 0 or actual_tokens < 0:
            raise ValueError("reserved_tokens and actual_tokens must not be negative")
        async with self._lock:
            bucket = self._refilled_bucket(key, Fraction(self._clock.now_seconds()))
            bucket.balance_tokens = min(
                Fraction(self._capacity_tokens),
                bucket.balance_tokens - (actual_tokens - reserved_tokens),
            )

    def _refilled_bucket(self, key: str, now_seconds: Fraction) -> _Bucket:
        """The key's bucket with the refill since its last update applied (a new key is full)."""
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(Fraction(self._capacity_tokens), now_seconds)
            self._buckets[key] = bucket
            return bucket
        # A clock that steps back (SystemClock after a time correction) gives no refill, and the
        # timestamp never moves back, so the stepped-back interval is not refilled twice.
        elapsed_seconds = max(Fraction(0), now_seconds - bucket.updated_seconds)
        bucket.balance_tokens = min(
            Fraction(self._capacity_tokens),
            bucket.balance_tokens + elapsed_seconds * self._refill_tokens_per_second,
        )
        bucket.updated_seconds = max(bucket.updated_seconds, now_seconds)
        return bucket

    def _decision(
        self, bucket: _Bucket, *, allowed: bool, retry_after_seconds: int | None
    ) -> Decision:
        missing_tokens = self._capacity_tokens - bucket.balance_tokens
        return Decision(
            allowed=allowed,
            limit_tokens=self._capacity_tokens,
            remaining_tokens=max(0, math.floor(bucket.balance_tokens)),
            retry_after_seconds=retry_after_seconds,
            reset_seconds=math.ceil(missing_tokens / self._refill_tokens_per_second),
        )
