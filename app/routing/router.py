"""Route selection and ordered fallback (ADR-0011).

`TableRouter.select` picks the targets for a request's model: the exact alias, else the default
route, else `UnknownModelError`. `run_route` tries those targets in order, each at most once, and
moves on only after a retryable `ProviderError` (ADR-0010). It never touches the limiter: the chat
route settles from the outcome it returns.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from app.api.models import ChatRequest, ChatResponse
from app.providers.base import Provider
from app.providers.errors import ProviderError
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


@dataclass(frozen=True, slots=True)
class Served:
    """A target answered. `fallbacks` counts the failed attempts before it."""

    completion: ChatResponse
    provider_name: str
    fallbacks: int


@dataclass(frozen=True, slots=True)
class RouteFailed:
    """The route ended without an answer. `charged` is true only for a `bad_response`, which the
    provider has probably billed, so the reservation stays charged (ADR-0010)."""

    charged: bool


type RouteOutcome = Served | RouteFailed


def upstream_request(request: ChatRequest, target: TargetConfig) -> ChatRequest:
    """The request as sent to `target`: its upstream model, or the client's when it has none.

    The client's request is never modified: a target with an upstream model gets a shallow copy
    with only `model` replaced, so every target sees the client's other fields.
    """
    if target.model is None:
        return request
    return request.model_copy(update={"model": target.model})


async def run_route(
    route: Route, providers: Mapping[str, Provider], request: ChatRequest
) -> RouteOutcome:
    """Try each target once, in order, until one answers or the route ends.

    Only the provider call is guarded: a missing registry entry is a bug, not a provider failure.
    """
    for fallbacks, target in enumerate(route):
        provider = providers[target.provider]
        try:
            completion = await provider.complete(upstream_request(request, target))
        except ProviderError as error:
            if error.retryable:
                continue
            return RouteFailed(charged=error.kind == "bad_response")
        except Exception:
            return RouteFailed(charged=False)
        return Served(completion=completion, provider_name=target.provider, fallbacks=fallbacks)
    return RouteFailed(charged=False)
