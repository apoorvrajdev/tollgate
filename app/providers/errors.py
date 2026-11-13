"""How a provider call failed, and whether the router may try the next target (ADR-0010).

An adapter raises `ProviderError` for every failure it can classify. The message holds only the kind
and the HTTP status: never a response body, which can echo the prompt, and never a key.
"""

from typing import Literal

ProviderErrorKind = Literal[
    "connection", "timeout", "rate_limited", "upstream_status", "bad_response"
]

# Kinds that may succeed on another target whatever the status. `upstream_status` is retryable
# only from 500 up (including 529), and `bad_response` never is: the provider answered and
# probably billed.
_ALWAYS_RETRYABLE: frozenset[ProviderErrorKind] = frozenset(
    {"connection", "timeout", "rate_limited"}
)
FIRST_RETRYABLE_STATUS = 500


class ProviderError(Exception):
    def __init__(self, kind: ProviderErrorKind, status_code: int | None = None) -> None:
        message = f"provider failed: {kind}"
        if status_code is not None:
            message += f" (HTTP {status_code})"
        super().__init__(message)
        self.kind: ProviderErrorKind = kind
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        if self.kind == "upstream_status":
            return self.status_code is not None and self.status_code >= FIRST_RETRYABLE_STATUS
        return self.kind in _ALWAYS_RETRYABLE
