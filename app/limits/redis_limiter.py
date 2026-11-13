"""The Redis token bucket (ADR-0006): one Lua script per call. Unit-tested against fakeredis.

Each API key has one Redis hash at `key_prefix + sha256(api_key)`, so no key written to Redis
contains the API key. The hash holds `balance_units` (tokens x 60000) and `updated_milliseconds`.
In those units one millisecond at `tokens_per_minute` refills exactly `tokens_per_minute` units, so
the script works only with integers below 2^53, which Lua's doubles hold exactly, and the results
agree with the exact-fraction reference in `memory.py`.

To stay in that range, the capacity and the rate are at most MAX_TOKENS (2^52 // 60000), and a
charge stops at a debt of MAX_TOKENS tokens. The in-memory limiter has no such floor; the two differ
only beyond 75 billion tokens of debt.

The time is the injected clock's value, rounded down to whole milliseconds. The clock is read
before the script runs, so two concurrent calls can reach Redis out of order; the script treats an
older time like a clock that stepped back (no refill, the timestamp never moves back), so nothing
is refilled twice. Every call sets the key to expire once the bucket would be full again, plus a
margin; an expired key starts full, which is then the correct balance.

Known limits, by design rather than by test: a key that disappears for any reason other than its
expiry (for example eviction, which fakeredis does not model) starts full again, and gateway hosts
whose clocks differ by more than the margin can expire a bucket shortly before it is full.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from redis.asyncio import Redis

from app.clock import Clock
from app.limits.limiter import Decision

BALANCE_UNITS_PER_TOKEN = 60_000  # milliseconds per minute
MILLISECONDS_PER_SECOND = 1000
MAX_TOKENS = 2**52 // BALANCE_UNITS_PER_TOKEN  # 75,059,993,789; also the deepest debt
DEFAULT_KEY_PREFIX = "tollgate:bucket:"
EXPIRY_MARGIN_MILLISECONDS = 60_000

_SCRIPT_SOURCE = (Path(__file__).parent / "token_bucket.lua").read_text(encoding="utf-8")
_BALANCE_PATTERN = re.compile(rf"(-?[0-9]{{1,16}})/{BALANCE_UNITS_PER_TOKEN}")


def milliseconds_from_seconds(seconds: float) -> int:
    """Whole milliseconds, rounded down from the exact value of the float."""
    return math.floor(Fraction(seconds) * MILLISECONDS_PER_SECOND)


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


@dataclass(frozen=True, slots=True)
class ScriptResult:
    allowed: bool
    balance_units: int


def parse_script_result(raw: object) -> ScriptResult:
    """The one place where the script's untyped reply becomes typed values.

    The reply must be `[1 or 0, "<n>/60000"]`. Anything else (a number for the balance, an exponent,
    another denominator) is rejected, so a formatting mistake in the script cannot pass silently.
    """
    if not isinstance(raw, list) or len(raw) != 2:
        raise TypeError(f"unexpected token bucket script reply: {raw!r}")
    flag, balance = raw
    if type(flag) is not int or flag not in (0, 1):
        raise ValueError(f"unexpected allowed flag in the token bucket script reply: {flag!r}")
    if isinstance(balance, bytes):
        balance = balance.decode("ascii")  # UnicodeDecodeError is a ValueError
    if not isinstance(balance, str):
        raise ValueError(f"the token bucket balance must be a string: {balance!r}")
    match = _BALANCE_PATTERN.fullmatch(balance)
    if match is None:
        raise ValueError(f"the token bucket balance is not '<n>/60000': {balance!r}")
    return ScriptResult(allowed=flag == 1, balance_units=int(match.group(1)))


class RedisRateLimiter:
    def __init__(
        self,
        redis: Redis,
        clock: Clock,
        tokens_per_minute: int,
        capacity_tokens: int,
        *,
        key_prefix: str = DEFAULT_KEY_PREFIX,
    ) -> None:
        if tokens_per_minute <= 0:
            raise ValueError("tokens_per_minute must be greater than zero")
        if capacity_tokens <= 0:
            raise ValueError("capacity_tokens must be greater than zero")
        if tokens_per_minute > MAX_TOKENS or capacity_tokens > MAX_TOKENS:
            raise ValueError(
                f"tokens_per_minute and capacity_tokens must be at most {MAX_TOKENS:,}"
            )
        self._clock = clock
        self._tokens_per_minute = tokens_per_minute
        self._capacity_tokens = capacity_tokens
        self._key_prefix = key_prefix
        self._script = redis.register_script(_SCRIPT_SOURCE)

    def bucket_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8", "surrogatepass")).hexdigest()
        return f"{self._key_prefix}{digest}"

    async def reserve(self, key: str, estimated_tokens: int) -> Decision:
        if estimated_tokens < 0:
            raise ValueError("estimated_tokens must not be negative")
        if estimated_tokens > self._capacity_tokens:
            # Waiting can never help, so there is no retry hint. A probe still applies the refill
            # and reports the balance, as the reference does.
            result = await self._run(key, "reserve", 0)
            return self._decision(result.balance_units, allowed=False, retry_after_seconds=None)
        amount_units = estimated_tokens * BALANCE_UNITS_PER_TOKEN
        result = await self._run(key, "reserve", amount_units)
        if result.allowed:
            return self._decision(result.balance_units, allowed=True, retry_after_seconds=None)
        wait_seconds = _ceil_div(amount_units - result.balance_units, self._units_per_second)
        return self._decision(result.balance_units, allowed=False, retry_after_seconds=wait_seconds)

    async def settle(self, key: str, reserved_tokens: int, actual_tokens: int) -> None:
        if reserved_tokens < 0 or actual_tokens < 0:
            raise ValueError("reserved_tokens and actual_tokens must not be negative")
        # A difference this large reaches the debt floor or the capacity from any balance, so the
        # clamp loses nothing and keeps the scaled amount exact in Lua.
        bound_tokens = self._capacity_tokens + MAX_TOKENS
        charge_tokens = max(-bound_tokens, min(bound_tokens, actual_tokens - reserved_tokens))
        await self._run(key, "settle", charge_tokens * BALANCE_UNITS_PER_TOKEN)

    @property
    def _units_per_second(self) -> int:
        return self._tokens_per_minute * MILLISECONDS_PER_SECOND

    async def _run(self, key: str, mode: str, amount_units: int) -> ScriptResult:
        now_milliseconds = milliseconds_from_seconds(self._clock.now_seconds())
        raw: object = await self._script(
            keys=[self.bucket_key(key)],
            args=[
                now_milliseconds,
                self._tokens_per_minute,
                self._capacity_tokens * BALANCE_UNITS_PER_TOKEN,
                -MAX_TOKENS * BALANCE_UNITS_PER_TOKEN,
                mode,
                amount_units,
                EXPIRY_MARGIN_MILLISECONDS,
            ],
        )
        return parse_script_result(raw)

    def _decision(
        self, balance_units: int, *, allowed: bool, retry_after_seconds: int | None
    ) -> Decision:
        missing_units = self._capacity_tokens * BALANCE_UNITS_PER_TOKEN - balance_units
        return Decision(
            allowed=allowed,
            limit_tokens=self._capacity_tokens,
            remaining_tokens=max(0, balance_units // BALANCE_UNITS_PER_TOKEN),
            retry_after_seconds=retry_after_seconds,
            reset_seconds=_ceil_div(missing_units, self._units_per_second),
        )
