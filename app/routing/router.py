"""Route selection and ordered fallback (ADR-0011).

`TableRouter.select` picks the targets for a request's model: the exact alias, else the default
route, else `UnknownModelError`. `run_route` tries those targets in order, each at most once, and
moves on only after a retryable `ProviderError` (ADR-0010). It never touches the limiter: the chat
route settles from the outcome it returns.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from app.api.models import ChatRequest, ChatResponse
from app.clock import MonotonicClock
from app.providers.base import Provider
from app.providers.errors import ProviderError, ReplyTooLargeError
from app.routing.config import RouteTable, TargetConfig

type Route = tuple[TargetConfig, ...]


class UnknownModelError(LookupError):
    """No alias matches and there is no default route. The message never shows the model."""

    def __init__(self) -> None:
        super().__init__("no route serves the requested model")


class Router(Protocol):
    def select(self, request: ChatRequest) -> Route: ...


class TableRouter:
    """Selects routes from a validated route table."""

    def __init__(self, table: RouteTable) -> None:
        self._table = table

    def select(self, request: ChatRequest) -> Route:
        route = self._table.routes.get(request.model)
        if route is not None:
            return route
        if self._table.default is not None:
            return self._table.default
        raise UnknownModelError()


type AttemptOutcome = Literal[
    "ok",
    "connection",
    "timeout",
    "rate_limited",
    "upstream_status",
    "bad_response",
    "reply_too_large",
    "error",
]


@dataclass(frozen=True, slots=True)
class Attempt:
    """One provider call: who, how it ended and how long it took (ADR-0016).

    `reply_too_large` is a `bad_response` whose cause was the size cap; `error` is an exception
    that is not a `ProviderError`. The duration runs on a monotonic clock.
    """

    provider_name: str
    outcome: AttemptOutcome
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class Served:
    """A target answered. `fallbacks` counts the failed attempts before it; `attempts` holds
    every call made, in order, the last one `ok`."""

    completion: ChatResponse
    provider_name: str
    fallbacks: int
    attempts: tuple[Attempt, ...]


@dataclass(frozen=True, slots=True)
class RouteFailed:
    """The route ended without an answer. `charged` is true only for a `bad_response`, which the
    provider has probably billed, so the reservation stays charged (ADR-0010). `attempts` holds
    every call made, in order."""

    charged: bool
    attempts: tuple[Attempt, ...]


type RouteOutcome = Served | RouteFailed


def upstream_request(request: ChatRequest, target: TargetConfig) -> ChatRequest:
    """The request as sent to `target`: its upstream model, or the client's when it has none.

    The client's request is never modified: a target with an upstream model gets a shallow copy
    with only `model` replaced, so every target sees the client's other fields.
    """
    if target.model is None:
        return request
    return request.model_copy(update={"model": target.model})


def outcome_of(error: ProviderError) -> AttemptOutcome:
    if isinstance(error, ReplyTooLargeError):
        return "reply_too_large"
    return error.kind


async def run_route(
    route: Route,
    providers: Mapping[str, Provider],
    request: ChatRequest,
    *,
    monotonic_clock: MonotonicClock,
) -> RouteOutcome:
    """Try each target once, in order, until one answers or the route ends.

    Only the provider call is guarded: a missing registry entry is a bug, not a provider failure.
    Each call is timed on `monotonic_clock`, read just before the call and again as it ends, and
    recorded as an `Attempt` whatever its outcome.
    """
    attempts: list[Attempt] = []
    for fallbacks, target in enumerate(route):
        provider = providers[target.provider]
        started_seconds = monotonic_clock.monotonic_seconds()
        try:
            completion = await provider.complete(upstream_request(request, target))
        except ProviderError as error:
            attempts.append(
                Attempt(
                    target.provider,
                    outcome_of(error),
                    monotonic_clock.monotonic_seconds() - started_seconds,
                )
            )
            if error.retryable:
                continue
            return RouteFailed(charged=error.kind == "bad_response", attempts=tuple(attempts))
        except Exception:
            attempts.append(
                Attempt(
                    target.provider, "error", monotonic_clock.monotonic_seconds() - started_seconds
                )
            )
            return RouteFailed(charged=False, attempts=tuple(attempts))
        attempts.append(
            Attempt(target.provider, "ok", monotonic_clock.monotonic_seconds() - started_seconds)
        )
        return Served(
            completion=completion,
            provider_name=target.provider,
            fallbacks=fallbacks,
            attempts=tuple(attempts),
        )
    return RouteFailed(charged=False, attempts=tuple(attempts))
