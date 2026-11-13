"""The rate limiter interface (ADR-0007, ADR-0008). Implementations: in memory, then Redis.

A limiter holds one token bucket per key. The caller reserves tokens before calling a provider and
settles with the provider's reported usage afterwards.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of a reservation, and the numbers the ADR-0008 headers are built from.

    - `allowed`: whether the reservation was taken from the bucket.
    - `limit_tokens`: the bucket capacity, on every decision.
    - `remaining_tokens`: the balance after the decision, rounded down and never below 0.
    - `retry_after_seconds`: whole seconds, rounded up, until the same reservation would succeed.
      `None` when allowed, and `None` when the reservation is larger than the capacity, because
      waiting can never help. A refusal that can succeed later is always at least 1.
    - `reset_seconds`: whole seconds, rounded up, until the bucket is full again. It is 0 for a full
      bucket and can exceed capacity / rate when the balance is negative.
    """

    allowed: bool
    limit_tokens: int
    remaining_tokens: int
    retry_after_seconds: int | None
    reset_seconds: int


class RateLimiter(Protocol):
    async def reserve(self, key: str, estimated_tokens: int) -> Decision:
        """Take `estimated_tokens` from the key's bucket if it holds that many.

        A refused reservation changes nothing except the refill. Raises ValueError for a negative
        amount.
        """
        ...

    async def settle(self, key: str, reserved_tokens: int, actual_tokens: int) -> None:
        """Charge or refund the difference between the actual usage and the reservation.

        A charge may take the balance below zero; a refund never lifts it above the capacity.
        Settling with `actual_tokens` of 0 refunds the whole reservation. Raises ValueError for a
        negative amount.
        """
        ...
