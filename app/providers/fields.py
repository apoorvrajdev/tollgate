"""The reply checks the HTTP adapters share (ADR-0010).

Each check returns the value or raises `ProviderError("bad_response", status)`. The error is raised
after any `try` block, never inside an `except`, so it has no `__context__`: the exception being
handled can hold the whole reply string, which can echo the prompt or the key.
"""

from collections.abc import Mapping

from app.providers.errors import ProviderError


def text(value: object, status: int) -> str:
    """A string that can be sent back as UTF-8 (empty is allowed), else a bad response."""
    if not isinstance(value, str):
        raise ProviderError("bad_response", status)
    encodable = True
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate from a JSON escape
        encodable = False
    if not encodable:
        raise ProviderError("bad_response", status)
    return value


def non_empty_text(value: object, status: int) -> str:
    """Like `text`, and the string must not be empty."""
    checked = text(value, status)
    if not checked:
        raise ProviderError("bad_response", status)
    return checked


def whole_number(value: object, status: int) -> int:
    """A whole number of at least 0 (not a bool), else a bad response."""
    if type(value) is not int or value < 0:
        raise ProviderError("bad_response", status)
    return value


def required_count(mapping: Mapping[str, object], key: str, status: int) -> int:
    """A token count that must be present (ADR-0010: a missing count is a bad response)."""
    if key not in mapping:
        raise ProviderError("bad_response", status)
    return whole_number(mapping[key], status)
