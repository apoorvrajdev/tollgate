"""The route table (ADR-0011): the configured providers and the targets that serve each model.

It is read from the JSON file named by TOLLGATE_ROUTES_FILE when the settings are read, validated in
full, and kept as read-only values. Every error names the variable and a field path, never a value
from the file or the environment. pydantic's own messages are not used, because some of them echo
the input (an unknown provider type, for one). Without the variable, the built-in table sends every
model to the mock provider.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

ROUTES_FILE_VAR = "TOLLGATE_ROUTES_FILE"
MIN_TARGETS = 1
MAX_TARGETS = 5
MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 60
PROVIDER_TYPES = ("mock", "ollama", "openai", "anthropic")
# A provider name is sent back as the x-tollgate-provider header, so it is limited to the visible
# ASCII characters (no space, control, CR, LF or non-ASCII character), which a header can carry.
PROVIDER_NAME_FIRST_CHAR = "!"
PROVIDER_NAME_LAST_CHAR = "~"
# A key pasted into api_key_env by mistake does not match (keys contain '-'), so it is rejected with
# a fixed reason and never printed (owner clarification, T-201).
ENV_VAR_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True)


class MockProviderConfig(BaseModel):
    model_config = _STRICT
    type: Literal["mock"]


class _HttpProviderConfig(BaseModel):
    model_config = _STRICT
    base_url: str | None = None
    timeout_seconds: int = Field(
        default=DEFAULT_TIMEOUT_SECONDS, ge=MIN_TIMEOUT_SECONDS, le=MAX_TIMEOUT_SECONDS
    )


class OllamaProviderConfig(_HttpProviderConfig):
    type: Literal["ollama"]


class OpenAIProviderConfig(_HttpProviderConfig):
    type: Literal["openai"]
    api_key_env: str = Field(pattern=ENV_VAR_NAME_PATTERN)


class AnthropicProviderConfig(_HttpProviderConfig):
    type: Literal["anthropic"]
    api_key_env: str = Field(pattern=ENV_VAR_NAME_PATTERN)
    default_max_tokens: int = Field(ge=1)


ProviderConfig = Annotated[
    MockProviderConfig | OllamaProviderConfig | OpenAIProviderConfig | AnthropicProviderConfig,
    Field(discriminator="type"),
]


class TargetConfig(BaseModel):
    """One attempt in a route. Without `model`, the client's model is passed through."""

    model_config = _STRICT
    provider: str
    model: str | None = Field(default=None, min_length=1)


_Targets = Annotated[list[TargetConfig], Field(min_length=MIN_TARGETS, max_length=MAX_TARGETS)]


class RouteTableFile(BaseModel):
    """The file as written. Each provider type allows exactly the settings ADR-0011 gives it."""

    model_config = _STRICT
    providers: dict[str, ProviderConfig]
    routes: dict[str, _Targets]
    default: _Targets | None = None


@dataclass(frozen=True, slots=True)
class RouteTable:
    """The validated table. `api_keys` maps a provider name to its key, where it has one."""

    providers: Mapping[str, ProviderConfig]
    routes: Mapping[str, tuple[TargetConfig, ...]]
    default: tuple[TargetConfig, ...] | None
    api_keys: Mapping[str, SecretStr]


BUILTIN_ROUTE_TABLE = RouteTable(
    providers=MappingProxyType({"mock": MockProviderConfig(type="mock")}),
    routes=MappingProxyType({}),
    default=(TargetConfig(provider="mock"),),
    api_keys=MappingProxyType({}),
)


class RouteTableError(ValueError):
    """An invalid route table. `app.settings` turns it into a SettingsError with the same parts."""

    def __init__(self, variable: str, reason: str) -> None:
        super().__init__(f"{variable}: {reason}")
        self.variable = variable
        self.reason = reason


_WRONG_TYPE_ERRORS = frozenset(
    {
        "string_type",
        "int_type",
        "dict_type",
        "list_type",
        "model_type",
        "model_attributes_type",
    }
)


def format_path(parts: Sequence[str | int]) -> str:
    """A field path such as `routes.fast[0].provider`."""
    text = ""
    for index, part in enumerate(parts):
        if isinstance(part, int):
            text += f"[{part}]"
        elif index == 0:
            text = part
        else:
            text += f".{part}"
    return text


def _file_error(parts: Sequence[str | int], reason: str) -> RouteTableError:
    path = format_path(parts)
    return RouteTableError(ROUTES_FILE_VAR, f"{path}: {reason}" if path else reason)


def _error_parts(loc: Sequence[str | int], error_type: str) -> list[str | int]:
    parts = list(loc)
    # pydantic puts the union tag after the provider name: ('providers', 'm', 'mock', 'base_url').
    if len(parts) >= 3 and parts[0] == "providers" and parts[2] in PROVIDER_TYPES:
        del parts[2]
    if error_type in ("union_tag_invalid", "union_tag_not_found"):
        parts.append("type")
    return parts


def _reason(error_type: str, context: Mapping[str, Any]) -> str:
    if error_type in ("missing", "union_tag_not_found"):
        return "is required"
    if error_type == "extra_forbidden":
        return "is not allowed"
    if error_type == "union_tag_invalid":
        return "must be one of " + ", ".join(PROVIDER_TYPES)
    if error_type in ("too_short", "too_long"):
        return f"must have {MIN_TARGETS} to {MAX_TARGETS} targets"
    if error_type == "greater_than_equal":
        return f"must be at least {context['ge']}"
    if error_type == "less_than_equal":
        return f"must be at most {context['le']}"
    if error_type == "string_pattern_mismatch":
        return "must be an environment variable name"
    if error_type == "string_too_short":
        return "must not be empty"
    if error_type in _WRONG_TYPE_ERRORS:
        return "has the wrong type"
    return "is invalid"


def _validation_error(exc: ValidationError) -> RouteTableError:
    # Only type, loc and the schema's bounds are read: msg and input can hold values from the file.
    first = exc.errors(include_url=False, include_input=False)[0]
    error_type = first["type"]
    parts = _error_parts(first["loc"], error_type)
    if not parts and error_type in _WRONG_TYPE_ERRORS:
        return _file_error(parts, "must contain a JSON object")
    return _file_error(parts, _reason(error_type, first.get("ctx", {})))


def _parse_json(text: str) -> Any:
    """Parse the file, rejecting duplicate keys (json keeps the last one silently)."""
    duplicates: dict[int, str] = {}
    # Every object the parser builds is kept alive until the walk ends. An object dropped as a
    # duplicate's value would otherwise be freed, and a later object could reuse its id.
    created: list[dict[str, Any]] = []

    def keep_first(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        created.append(obj)
        for key, value in pairs:
            if key in obj:
                duplicates.setdefault(id(obj), key)
            else:
                obj[key] = value
        return obj

    try:
        data = json.loads(text, object_pairs_hook=keep_first)
    except json.JSONDecodeError as exc:
        reason = f"is not valid JSON (line {exc.lineno}, column {exc.colno})"
        raise RouteTableError(ROUTES_FILE_VAR, reason) from None
    except (ValueError, RecursionError):
        raise RouteTableError(ROUTES_FILE_VAR, "is not valid JSON") from None
    duplicate = _find_duplicate(data, [], duplicates)
    if duplicate is not None:
        raise _file_error(duplicate, "is a duplicate key")
    return data


def _find_duplicate(
    node: Any, parts: list[str | int], duplicates: Mapping[int, str]
) -> list[str | int] | None:
    """The path of the first duplicate key, outer objects first, then in document order.

    The walk keeps its own stack, so a file nested deeper than Python's recursion limit (which the
    JSON parser can still accept) cannot raise RecursionError here.
    """
    stack: list[tuple[Any, list[str | int]]] = [(node, parts)]
    while stack:
        current, path = stack.pop()
        children: list[tuple[Any, list[str | int]]] = []
        if isinstance(current, dict):
            key = duplicates.get(id(current))
            if key is not None:
                return [*path, key]
            children = [(child, [*path, name]) for name, child in current.items()]
        elif isinstance(current, list):
            children = [(child, [*path, index]) for index, child in enumerate(current)]
        stack.extend(reversed(children))
    return None


def _read_text(raw_path: str) -> str:
    # The path is the variable's value and can hold a user name, so no message shows it.
    try:
        content = Path(raw_path).read_bytes()
    except (OSError, ValueError):  # ValueError: a NUL character in the path
        raise RouteTableError(ROUTES_FILE_VAR, "the file could not be read") from None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise RouteTableError(ROUTES_FILE_VAR, "the file is not valid UTF-8") from None
    if text.startswith("\ufeff"):
        reason = "the file must be UTF-8 without a byte order mark"
        raise RouteTableError(ROUTES_FILE_VAR, reason)
    return text


def _is_visible_ascii(name: str) -> bool:
    return all(PROVIDER_NAME_FIRST_CHAR <= char <= PROVIDER_NAME_LAST_CHAR for char in name)


def _check_names(table: RouteTableFile) -> None:
    # An empty alias can never match a request (its model has at least one character), and an
    # empty provider name is legal JSON but only confuses (owner decision, T-201).
    if "" in table.providers:
        raise _file_error(["providers"], "has an empty provider name")
    # The name is the value that cannot be printed safely, so the reason never shows it (T-203).
    if not all(_is_visible_ascii(name) for name in table.providers):
        reason = "has a provider name that is not made only of visible ASCII characters (! to ~)"
        raise _file_error(["providers"], reason)
    if "" in table.routes:
        raise _file_error(["routes"], "has an empty alias")


def _check_targets(table: RouteTableFile) -> None:
    reason = "names an undefined provider"
    for alias, targets in table.routes.items():
        for index, target in enumerate(targets):
            if target.provider not in table.providers:
                raise _file_error(["routes", alias, index, "provider"], reason)
    for index, target in enumerate(table.default or ()):
        if target.provider not in table.providers:
            raise _file_error(["default", index, "provider"], reason)


def _read_keys(table: RouteTableFile, environ: Mapping[str, str]) -> dict[str, SecretStr]:
    keys: dict[str, SecretStr] = {}
    for name, provider in table.providers.items():
        if not isinstance(provider, OpenAIProviderConfig | AnthropicProviderConfig):
            continue
        value = environ.get(provider.api_key_env)
        if value is None or not value.strip():
            field = format_path(["providers", name, "api_key_env"])
            reason = f"is required by {ROUTES_FILE_VAR} {field} and must not be empty"
            raise RouteTableError(provider.api_key_env, reason)
        keys[name] = SecretStr(value.strip())
    return keys


def load_route_table(environ: Mapping[str, str]) -> RouteTable:
    """The table named by TOLLGATE_ROUTES_FILE in `environ`, or the built-in table without it.

    Keys are read from the same mapping. Raises RouteTableError.
    """
    raw_path = environ.get(ROUTES_FILE_VAR)
    if raw_path is None:
        return BUILTIN_ROUTE_TABLE
    if not raw_path.strip():
        raise RouteTableError(ROUTES_FILE_VAR, "is set but empty")
    data = _parse_json(_read_text(raw_path.strip()))
    try:
        table = RouteTableFile.model_validate(data)
    except ValidationError as exc:
        raise _validation_error(exc) from None
    _check_names(table)
    _check_targets(table)
    keys = _read_keys(table, environ)
    return RouteTable(
        providers=MappingProxyType(dict(table.providers)),
        routes=MappingProxyType({alias: tuple(targets) for alias, targets in table.routes.items()}),
        default=None if table.default is None else tuple(table.default),
        api_keys=MappingProxyType(keys),
    )
