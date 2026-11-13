"""The route table file (ADR-0011, T-201): loading, every validation rule, and no leaked values."""

import json
import traceback
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routing.config import (
    AnthropicProviderConfig,
    MockProviderConfig,
    OllamaProviderConfig,
    OpenAIProviderConfig,
    TargetConfig,
)
from app.settings import Settings, SettingsError
from tests.fakes import AUTH_HEADERS, FakeClock, make_settings

VAR = "TOLLGATE_ROUTES_FILE"
VALUE = "SENTINEL-val-4e1d"
KEY = "SENTINEL-key-9b7c"
BASE_ENV = {"TOLLGATE_API_KEYS": "k1", "TOLLGATE_TOKENS_PER_MINUTE": "60"}
TYPES_REASON = "must be one of mock, ollama, openai, anthropic"
TARGETS_REASON = "must have 1 to 5 targets"


def write_json(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def write_text(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "routes.json"
    path.write_bytes(text.encode("utf-8"))
    return path


def env(path: Path | str, **extra: str) -> dict[str, str]:
    return {**BASE_ENV, VAR: str(path), **extra}


def error_for(environ: dict[str, str]) -> SettingsError:
    with pytest.raises(SettingsError) as raised:
        Settings.from_env(environ)
    return raised.value


def assert_clean(error: BaseException, *sentinels: str) -> None:
    """No sentinel in the message or the formatted traceback, and no chained exception."""
    text = str(error) + "".join(traceback.format_exception(error))
    for sentinel in sentinels:
        assert sentinel not in text
    assert error.__cause__ is None
    assert error.__suppress_context__


def table_file(**overrides: Any) -> dict[str, Any]:
    """A small valid file: one mock provider and one route to it."""
    data: dict[str, Any] = {
        "providers": {"m": {"type": "mock"}},
        "routes": {"fast": [{"provider": "m"}]},
    }
    data.update(overrides)
    return data


def with_provider(provider: dict[str, Any]) -> dict[str, Any]:
    return table_file(providers={"p": provider, "m": {"type": "mock"}})


FULL_FILE: dict[str, Any] = {
    "providers": {
        "local": {
            "type": "ollama",
            "base_url": "http://ollama.internal:11434",
            "timeout_seconds": 30,
        },
        "cloud": {"type": "openai", "api_key_env": "CLOUD_KEY"},
        "claude": {"type": "anthropic", "api_key_env": "CLAUDE_KEY", "default_max_tokens": 1024},
        "m": {"type": "mock"},
    },
    "routes": {
        "fast": [
            {"provider": "local", "model": "llama3.2"},
            {"provider": "cloud", "model": "gpt-4o-mini"},
        ],
        "smart": [{"provider": "claude", "model": "claude-x"}, {"provider": "cloud"}],
    },
    "default": [{"provider": "m"}],
}
FULL_KEYS = {"CLOUD_KEY": "test-cloud-value", "CLAUDE_KEY": "test-claude-value"}


# Criterion 1: a valid file loads into the expected table.


def test_valid_file_loads_into_the_exact_table(tmp_path: Path) -> None:
    table = Settings.from_env(env(write_json(tmp_path, FULL_FILE), **FULL_KEYS)).route_table
    assert list(table.providers) == ["local", "cloud", "claude", "m"]
    assert table.providers["local"] == OllamaProviderConfig(
        type="ollama", base_url="http://ollama.internal:11434", timeout_seconds=30
    )
    assert table.providers["cloud"] == OpenAIProviderConfig(
        type="openai", api_key_env="CLOUD_KEY", base_url=None, timeout_seconds=60
    )
    assert table.providers["claude"] == AnthropicProviderConfig(
        type="anthropic", api_key_env="CLAUDE_KEY", default_max_tokens=1024
    )
    assert table.providers["m"] == MockProviderConfig(type="mock")
    assert list(table.routes) == ["fast", "smart"]
    assert table.routes["fast"] == (
        TargetConfig(provider="local", model="llama3.2"),
        TargetConfig(provider="cloud", model="gpt-4o-mini"),
    )
    assert table.routes["smart"] == (
        TargetConfig(provider="claude", model="claude-x"),
        TargetConfig(provider="cloud", model=None),
    )
    assert table.default == (TargetConfig(provider="m", model=None),)
    keys = {name: key.get_secret_value() for name, key in table.api_keys.items()}
    assert keys == {"cloud": "test-cloud-value", "claude": "test-claude-value"}


def test_file_without_default_has_no_default_route(tmp_path: Path) -> None:
    table = Settings.from_env(env(write_json(tmp_path, table_file()))).route_table
    assert table.default is None
    assert table.api_keys == {}


def test_provider_key_is_trimmed(tmp_path: Path) -> None:
    data = table_file(
        providers={"cloud": {"type": "openai", "api_key_env": "CLOUD_KEY"}, "m": {"type": "mock"}}
    )
    table = Settings.from_env(
        env(write_json(tmp_path, data), CLOUD_KEY=" test-key-value \n")
    ).route_table
    assert table.api_keys["cloud"].get_secret_value() == "test-key-value"


def test_route_table_is_read_only(tmp_path: Path) -> None:
    table = Settings.from_env(env(write_json(tmp_path, table_file()))).route_table
    with pytest.raises(TypeError):
        table.routes["other"] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        table.providers["other"] = MockProviderConfig(type="mock")  # type: ignore[index]


# Criterion 2: each invalid file fails naming the variable and the field path.

OLLAMA = {"type": "ollama"}
OPENAI = {"type": "openai", "api_key_env": "CLOUD_KEY"}
ANTHROPIC = {"type": "anthropic", "api_key_env": "CLOUD_KEY", "default_max_tokens": 10}
SIX_TARGETS = [{"provider": "m"}] * 6

INVALID_FILES: list[tuple[str, dict[str, Any], str]] = [
    ("top-level-list", [], "must contain a JSON object"),  # type: ignore[list-item]
    ("unknown-top-level", table_file(extra=1), "extra: is not allowed"),
    ("lookalike-Providers", {**table_file(), "Providers": {}}, "Providers: is not allowed"),
    ("lookalike-Default", {**table_file(), "Default": []}, "Default: is not allowed"),
    ("providers-missing", {"routes": {}}, "providers: is required"),
    ("routes-missing", {"providers": {}}, "routes: is required"),
    (
        "unknown-on-mock",
        with_provider({"type": "mock", "colour": 1}),
        "providers.p.colour: is not allowed",
    ),
    (
        "unknown-on-ollama",
        with_provider({**OLLAMA, "colour": 1}),
        "providers.p.colour: is not allowed",
    ),
    (
        "unknown-on-openai",
        with_provider({**OPENAI, "colour": 1}),
        "providers.p.colour: is not allowed",
    ),
    (
        "unknown-on-anthropic",
        with_provider({**ANTHROPIC, "colour": 1}),
        "providers.p.colour: is not allowed",
    ),
    (
        "unknown-on-target",
        table_file(routes={"fast": [{"provider": "m", "Model": "x"}]}),
        "routes.fast[0].Model: is not allowed",
    ),
    ("type-Mock", with_provider({"type": "Mock"}), f"providers.p.type: {TYPES_REASON}"),
    ("type-MOCK", with_provider({"type": "MOCK"}), f"providers.p.type: {TYPES_REASON}"),
    ("type-leading-space", with_provider({"type": " mock"}), f"providers.p.type: {TYPES_REASON}"),
    ("type-unknown", with_provider({"type": "gemini"}), f"providers.p.type: {TYPES_REASON}"),
    ("type-number", with_provider({"type": 1}), f"providers.p.type: {TYPES_REASON}"),
    ("type-missing", with_provider({}), "providers.p.type: is required"),
    ("provider-not-object", with_provider(5), "providers.p: has the wrong type"),  # type: ignore[arg-type]
    (
        "undefined-provider",
        table_file(routes={"fast": [{"provider": "m"}, {"provider": "nope"}]}),
        "routes.fast[1].provider: names an undefined provider",
    ),
    (
        "undefined-provider-in-default",
        table_file(default=[{"provider": "nope"}]),
        "default[0].provider: names an undefined provider",
    ),
    ("empty-route", table_file(routes={"fast": []}), f"routes.fast: {TARGETS_REASON}"),
    ("six-targets", table_file(routes={"fast": SIX_TARGETS}), f"routes.fast: {TARGETS_REASON}"),
    ("empty-default", table_file(default=[]), f"default: {TARGETS_REASON}"),
    ("six-default-targets", table_file(default=SIX_TARGETS), f"default: {TARGETS_REASON}"),
    (
        "route-not-list",
        table_file(routes={"fast": {"provider": "m"}}),
        "routes.fast: has the wrong type",
    ),
    (
        "timeout-4",
        with_provider({**OLLAMA, "timeout_seconds": 4}),
        "providers.p.timeout_seconds: must be at least 5",
    ),
    (
        "timeout-601",
        with_provider({**OLLAMA, "timeout_seconds": 601}),
        "providers.p.timeout_seconds: must be at most 600",
    ),
    (
        "timeout-string",
        with_provider({**OLLAMA, "timeout_seconds": "60"}),
        "providers.p.timeout_seconds: has the wrong type",
    ),
    (
        "timeout-float",
        with_provider({**OLLAMA, "timeout_seconds": 60.0}),
        "providers.p.timeout_seconds: has the wrong type",
    ),
    (
        "base-url-on-mock",
        with_provider({"type": "mock", "base_url": "x"}),
        "providers.p.base_url: is not allowed",
    ),
    (
        "timeout-on-mock",
        with_provider({"type": "mock", "timeout_seconds": 60}),
        "providers.p.timeout_seconds: is not allowed",
    ),
    (
        "max-tokens-missing-on-anthropic",
        with_provider({"type": "anthropic", "api_key_env": "CLOUD_KEY"}),
        "providers.p.default_max_tokens: is required",
    ),
    (
        "max-tokens-zero-on-anthropic",
        with_provider({**ANTHROPIC, "default_max_tokens": 0}),
        "providers.p.default_max_tokens: must be at least 1",
    ),
    (
        "max-tokens-on-openai",
        with_provider({**OPENAI, "default_max_tokens": 10}),
        "providers.p.default_max_tokens: is not allowed",
    ),
    (
        "max-tokens-on-ollama",
        with_provider({**OLLAMA, "default_max_tokens": 10}),
        "providers.p.default_max_tokens: is not allowed",
    ),
    (
        "max-tokens-on-mock",
        with_provider({"type": "mock", "default_max_tokens": 10}),
        "providers.p.default_max_tokens: is not allowed",
    ),
    (
        "key-env-missing-on-openai",
        with_provider({"type": "openai"}),
        "providers.p.api_key_env: is required",
    ),
    (
        "key-env-missing-on-anthropic",
        with_provider({"type": "anthropic", "default_max_tokens": 10}),
        "providers.p.api_key_env: is required",
    ),
    (
        "key-env-on-mock",
        with_provider({"type": "mock", "api_key_env": "CLOUD_KEY"}),
        "providers.p.api_key_env: is not allowed",
    ),
    (
        "key-env-on-ollama",
        with_provider({**OLLAMA, "api_key_env": "CLOUD_KEY"}),
        "providers.p.api_key_env: is not allowed",
    ),
    # Field and provider names that equal a provider type keep their place in the path.
    (
        "field-named-mock",
        with_provider({"type": "mock", "mock": 1}),
        "providers.p.mock: is not allowed",
    ),
    (
        "field-named-ollama",
        with_provider({**OLLAMA, "ollama": 1}),
        "providers.p.ollama: is not allowed",
    ),
    (
        "field-named-openai",
        with_provider({**OPENAI, "openai": 1}),
        "providers.p.openai: is not allowed",
    ),
    (
        "provider-named-ollama",
        table_file(providers={"ollama": {"type": "mock", "colour": 1}, "m": {"type": "mock"}}),
        "providers.ollama.colour: is not allowed",
    ),
    (
        "provider-named-openai",
        table_file(
            providers={
                "openai": {"type": "anthropic", "api_key_env": "CLOUD_KEY"},
                "m": {"type": "mock"},
            }
        ),
        "providers.openai.default_max_tokens: is required",
    ),
    (
        "provider-named-mock-not-object",
        table_file(providers={"mock": 5, "m": {"type": "mock"}}),
        "providers.mock: has the wrong type",
    ),
    # Empty names are rejected (owner decision, T-201).
    (
        "empty-provider-name",
        table_file(providers={"": {"type": "mock"}, "m": {"type": "mock"}}),
        "providers: has an empty provider name",
    ),
    (
        "empty-alias",
        table_file(routes={"fast": [{"provider": "m"}], "": [{"provider": "m"}]}),
        "routes: has an empty alias",
    ),
    (
        "empty-model",
        table_file(routes={"fast": [{"provider": "m", "model": ""}]}),
        "routes.fast[0].model: must not be empty",
    ),
    (
        "empty-model-in-default",
        table_file(default=[{"provider": "m", "model": ""}]),
        "default[0].model: must not be empty",
    ),
]

KEY_ENV_NAME_REASON = "providers.p.api_key_env: must be an environment variable name"


@pytest.mark.parametrize(
    ("data", "message"),
    [pytest.param(data, message, id=name) for name, data, message in INVALID_FILES],
)
def test_invalid_file_fails_naming_the_variable_and_the_field_path(
    tmp_path: Path, data: Any, message: str
) -> None:
    error = error_for(env(write_json(tmp_path, data), CLOUD_KEY="test-key-value"))
    assert error.variable == VAR
    assert str(error) == f"{VAR}: {message}"


@pytest.mark.parametrize(
    "name",
    ["pasted-key-abc123", "1KEY", "CLOUD KEY", "CLOUD-KEY", "", "CLOUD_KEY\n", "CLÉ"],
)
def test_api_key_env_must_be_a_variable_name(tmp_path: Path, name: str) -> None:
    for provider in (
        {"type": "openai", "api_key_env": name},
        {"type": "anthropic", "api_key_env": name, "default_max_tokens": 10},
    ):
        error = error_for(
            env(write_json(tmp_path, with_provider(provider)), **{name: "x"} if name else {})
        )
        assert str(error) == f"{VAR}: {KEY_ENV_NAME_REASON}"
        assert_clean(error, "pasted-key-abc123")


@pytest.mark.parametrize("name", ["CLOUD_KEY", "_KEY", "k", "KEY_2"])
def test_api_key_env_accepts_variable_names(tmp_path: Path, name: str) -> None:
    data = with_provider({"type": "openai", "api_key_env": name})
    table = Settings.from_env(
        env(write_json(tmp_path, data), **{name: "test-key-value"})
    ).route_table
    assert table.api_keys["p"].get_secret_value() == "test-key-value"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param('{"providers": }', "is not valid JSON (line 1, column 15)", id="malformed"),
        pytest.param(
            '{"providers": {}, "routes": {}', "is not valid JSON (line 1, column 31)", id="unclosed"
        ),
        pytest.param(
            '{"providers": {}, "providers": {}, "routes": {}}',
            "providers: is a duplicate key",
            id="duplicate-top-level",
        ),
        pytest.param(
            '{"providers": {"local": {"type": "mock"}, "local": {"type": "mock"}}, "routes": {}}',
            "providers.local: is a duplicate key",
            id="duplicate-provider-name",
        ),
        pytest.param(
            '{"providers": {"m": {"type": "mock"}}, '
            '"routes": {"fast": [{"provider": "m"}], "fast": [{"provider": "m"}]}}',
            "routes.fast: is a duplicate key",
            id="duplicate-alias",
        ),
        pytest.param(
            '{"providers": {"local": {"type": "mock", "type": "mock"}}, "routes": {}}',
            "providers.local.type: is a duplicate key",
            id="duplicate-provider-field",
        ),
        pytest.param(
            '{"providers": {"m": {"type": "mock"}}, '
            '"routes": {"fast": [{"provider": "m", "provider": "m"}]}}',
            "routes.fast[0].provider: is a duplicate key",
            id="duplicate-target-field",
        ),
        # The dropped duplicate value has a duplicate of its own; its id must not be mistaken for
        # a later object's (found in review: a freed dict's id was reused by the top level).
        pytest.param(
            '{"routes": {}, "providers": {"p": {"type": "mock"}, '
            '"p": {"type": "mock", "type": "mock"}}}',
            "providers.p: is a duplicate key",
            id="duplicate-whose-dropped-value-has-a-duplicate",
        ),
        pytest.param(
            '{"providers": {}, "routes": {}, "x": ' + "1" * 5000 + "}",
            "is not valid JSON",
            id="integer-too-long",
        ),
        # The json parser's depth limit is CPython's C recursion budget, which differs by platform
        # (about 3000 on Windows, higher on Linux), so this nests far beyond any of them.
        pytest.param(
            "[" * 100_000 + "]" * 100_000, "is not valid JSON", id="nested-beyond-the-parser"
        ),
        # Two duplicates: the outer object's is reported first, then the earlier sibling's.
        pytest.param(
            '{"providers": {"a": {"type": "mock", "type": "mock"}}, "routes": {}, "routes": {}}',
            "routes: is a duplicate key",
            id="two-duplicates-outer-first",
        ),
        pytest.param(
            '{"providers": {"a": {"type": "mock", "type": "mock"}, '
            '"b": {"type": "mock", "type": "mock"}}, "routes": {}}',
            "providers.a.type: is a duplicate key",
            id="two-duplicates-document-order",
        ),
    ],
)
def test_malformed_or_duplicated_text_fails_with_its_position(
    tmp_path: Path, text: str, message: str
) -> None:
    error = error_for(env(write_text(tmp_path, text)))
    assert error.variable == VAR
    assert str(error) == f"{VAR}: {message}"


def test_file_that_is_not_utf8_fails(tmp_path: Path) -> None:
    path = tmp_path / "routes.json"
    path.write_bytes(b"\xff{}")
    assert str(error_for(env(path))) == f"{VAR}: the file is not valid UTF-8"


def test_file_with_a_byte_order_mark_fails(tmp_path: Path) -> None:
    path = tmp_path / "routes.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(table_file()).encode("utf-8"))
    message = f"{VAR}: the file must be UTF-8 without a byte order mark"
    assert str(error_for(env(path))) == message


@pytest.mark.parametrize("raw", ["", "  ", "\t\n"])
def test_blank_variable_is_an_error_not_a_fallback(raw: str) -> None:
    error = error_for({**BASE_ENV, VAR: raw})
    assert str(error) == f"{VAR}: is set but empty"


def test_unreadable_path_fails_without_showing_the_path(tmp_path: Path) -> None:
    directory = tmp_path / "SENTINEL-dir-3c"
    for path in (directory / "missing.json", tmp_path):
        error = error_for(env(path))
        assert str(error) == f"{VAR}: the file could not be read"
        assert_clean(error, "SENTINEL-dir-3c", str(tmp_path))


@pytest.mark.parametrize("depth", [1000, 1500, 2500])
def test_nesting_deeper_than_the_recursion_limit_is_a_settings_error(
    tmp_path: Path, depth: int
) -> None:
    # The JSON parser accepts these depths; the duplicate walk must not raise RecursionError.
    nested = "[" * depth + "]" * depth
    error = error_for(
        env(write_text(tmp_path, '{"providers": {}, "routes": {}, "x": ' + nested + "}"))
    )
    assert str(error) == f"{VAR}: x: is not allowed"


def test_nested_duplicate_deeper_than_the_recursion_limit_is_found(tmp_path: Path) -> None:
    depth = 1500
    text = (
        '{"providers": {}, "routes": {}, "x": '
        + "[" * depth
        + '{"a": 1, "a": 2}'
        + "]" * depth
        + "}"
    )
    error = error_for(env(write_text(tmp_path, text)))
    assert str(error) == f"{VAR}: x" + "[0]" * depth + ".a: is a duplicate key"


def test_path_with_a_nul_character_cannot_be_read() -> None:
    error = error_for({**BASE_ENV, VAR: "routes\x00.json"})
    assert str(error) == f"{VAR}: the file could not be read"
    assert_clean(error, "routes")


def test_path_is_trimmed_like_other_settings(tmp_path: Path) -> None:
    path = write_json(tmp_path, table_file())
    table = Settings.from_env({**BASE_ENV, VAR: f"  {path}  "}).route_table
    assert list(table.routes) == ["fast"]


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(with_provider({"type": VALUE}), id="type"),
        pytest.param(with_provider({**OLLAMA, "timeout_seconds": VALUE}), id="timeout"),
        pytest.param(with_provider({"type": "mock", "base_url": VALUE}), id="base-url-on-mock"),
        pytest.param(table_file(extra=VALUE), id="unknown-field-value"),
        pytest.param(table_file(routes={"fast": [{"provider": VALUE}]}), id="undefined-provider"),
        pytest.param(table_file(routes={"fast": VALUE}), id="route-string"),
        pytest.param(with_provider({"type": "openai", "api_key_env": VALUE}), id="key-env-name"),
        pytest.param(table_file(default=[{"provider": "m", "model": 5}]), id="model-number"),
    ],
)
def test_errors_never_contain_a_value_from_the_file(tmp_path: Path, data: Any) -> None:
    assert_clean(error_for(env(write_json(tmp_path, data))), VALUE)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(f'{{"providers": "{VALUE}" ', id="malformed"),
        pytest.param(
            f'{{"providers": {{}}, "routes": {{}}, "x": "{VALUE}", "x": "{VALUE}"}}', id="duplicate"
        ),
    ],
)
def test_text_errors_never_contain_a_value_from_the_file(tmp_path: Path, text: str) -> None:
    assert_clean(error_for(env(write_text(tmp_path, text))), VALUE)


# Criterion 3: provider keys come from the variables the file names.


@pytest.mark.parametrize(
    "value", [None, "", "   ", "\t\n"], ids=["unset", "empty", "spaces", "whitespace"]
)
def test_key_variable_unset_empty_or_blank_fails_naming_it(
    tmp_path: Path, value: str | None
) -> None:
    keys = (
        {"CLAUDE_KEY": "test-claude-value"}
        if value is None
        else {"CLOUD_KEY": value, "CLAUDE_KEY": "test-claude-value"}
    )
    error = error_for(env(write_json(tmp_path, FULL_FILE), **keys))
    assert error.variable == "CLOUD_KEY"
    expected = f"CLOUD_KEY: is required by {VAR} providers.cloud.api_key_env and must not be empty"
    assert str(error) == expected


def test_key_variable_lookup_is_exact(tmp_path: Path) -> None:
    error = error_for(
        env(
            write_json(tmp_path, FULL_FILE),
            cloud_key="test-key-value",
            CLAUDE_KEY="test-claude-value",
        )
    )
    assert error.variable == "CLOUD_KEY"


def test_keys_never_appear_in_repr_or_errors(tmp_path: Path) -> None:
    path = write_json(tmp_path, FULL_FILE)
    settings = Settings.from_env(env(path, CLOUD_KEY=KEY, CLAUDE_KEY=KEY))
    for text in (repr(settings), str(settings), repr(settings.route_table)):
        assert KEY not in text
        assert "**********" in text
    error = error_for(env(path, CLOUD_KEY=KEY))
    assert error.variable == "CLAUDE_KEY"
    assert_clean(error, KEY)


# Criterion 4: without the variable, the built-in table applies.


def test_without_the_variable_the_builtin_table_applies() -> None:
    for table in (Settings.from_env(BASE_ENV).route_table, make_settings().route_table):
        assert table.providers == {"mock": MockProviderConfig(type="mock")}
        assert table.routes == {}
        assert table.default == (TargetConfig(provider="mock", model=None),)
        assert table.api_keys == {}


def test_table_and_keys_come_only_from_the_given_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_json(tmp_path, FULL_FILE)
    monkeypatch.setenv(VAR, str(path))
    monkeypatch.setenv("CLOUD_KEY", "test-cloud-value")
    assert Settings.from_env(BASE_ENV).route_table.routes == {}
    error = error_for(env(path, CLAUDE_KEY="test-claude-value"))
    assert error.variable == "CLOUD_KEY"


def test_create_app_stops_at_startup_on_a_bad_route_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in {
        **BASE_ENV,
        VAR: str(write_json(tmp_path, table_file(routes={"fast": SIX_TARGETS}))),
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError) as raised:
        create_app()
    assert raised.value.variable == VAR


# The accepted side of each rule.


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(table_file(routes={"fast": [{"provider": "m"}] * 5}), id="five-targets"),
        pytest.param(table_file(default=[{"provider": "m"}] * 5), id="five-default-targets"),
        pytest.param(table_file(default=None), id="null-default"),
        pytest.param(table_file(providers={"m": {"type": "mock"}}, routes={}), id="no-routes"),
        pytest.param(with_provider({**OLLAMA, "timeout_seconds": 5}), id="timeout-5"),
        pytest.param(with_provider({**OLLAMA, "timeout_seconds": 600}), id="timeout-600"),
        pytest.param(with_provider({**OLLAMA, "base_url": "http://h:1"}), id="ollama-settings"),
        pytest.param(
            with_provider({**OPENAI, "base_url": "http://h:1", "timeout_seconds": 9}),
            id="openai-settings",
        ),
        pytest.param(
            with_provider({**ANTHROPIC, "base_url": "http://h:1", "timeout_seconds": 9}),
            id="anthropic-settings",
        ),
        pytest.param(
            table_file(
                providers={"q": {"type": "mock"}}, routes={"a": [{"provider": "q", "model": "x"}]}
            ),
            id="one-character-names",
        ),
    ],
)
def test_valid_variants_load(tmp_path: Path, data: Any) -> None:
    Settings.from_env(env(write_json(tmp_path, data), CLOUD_KEY="test-key-value"))


# Provider names must be sendable as the x-tollgate-provider header (T-203).

NAME_REASON = "has a provider name that is not made only of visible ASCII characters (! to ~)"
NAME_SENTINEL = "SENTINEL-name-5d2a"
EVERY_VISIBLE_ASCII = "".join(chr(code) for code in range(0x21, 0x7F))
CHAT_URL = "/v1/chat/completions"


def mock_providers(*names: str) -> dict[str, Any]:
    return {name: {"type": "mock"} for name in names}


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(" ", id="space"),
        pytest.param("\x00", id="nul"),
        pytest.param("\x01", id="control-1"),
        pytest.param("\t", id="tab"),
        pytest.param("\n", id="lf"),
        pytest.param("\r", id="cr"),
        pytest.param("\x1f", id="control-1f"),
        pytest.param("\x7f", id="delete"),
        pytest.param("\x80", id="c1-control"),
        pytest.param("\xa0", id="no-break-space"),
        pytest.param("\xe9", id="accented"),
        pytest.param("\uff21", id="fullwidth-letter"),
        pytest.param("\u2028", id="line-separator"),
        pytest.param("\U0001f600", id="emoji"),
    ],
)
def test_provider_name_with_an_unsendable_character_fails_without_naming_it(
    tmp_path: Path, bad: str
) -> None:
    name = f"{NAME_SENTINEL}{bad}x"
    data = table_file(providers=mock_providers(name), routes={})
    error = error_for(env(write_json(tmp_path, data)))
    assert error.variable == VAR
    assert str(error) == f"{VAR}: providers: {NAME_REASON}"
    assert_clean(error, NAME_SENTINEL)


@pytest.mark.parametrize(
    "name",
    [" ", "\x00", "\x7f", "\xe9", " ab", "a b", "ab ", "ab\n", "\nab", "ab\r", "\x7fab"],
    ids=repr,
)
def test_a_bad_character_fails_in_any_position_and_as_the_only_character(
    tmp_path: Path, name: str
) -> None:
    data = table_file(providers=mock_providers(name), routes={})
    error = error_for(env(write_json(tmp_path, data)))
    assert str(error) == f"{VAR}: providers: {NAME_REASON}"


def test_every_provider_name_is_checked_not_only_the_first(tmp_path: Path) -> None:
    data = table_file(providers=mock_providers("good", "bad name"), routes={})
    assert str(error_for(env(write_json(tmp_path, data)))) == f"{VAR}: providers: {NAME_REASON}"


def test_empty_provider_name_keeps_its_own_message_even_beside_a_bad_name(tmp_path: Path) -> None:
    data = table_file(providers=mock_providers("", "bad name"), routes={})
    error = error_for(env(write_json(tmp_path, data)))
    assert str(error) == f"{VAR}: providers: has an empty provider name"


@pytest.mark.parametrize(
    "name",
    ["!", "~", '"', "\\", "0", "a", "A", "a-b_c.d:e", "%41", EVERY_VISIBLE_ASCII],
    ids=lambda name: "every-visible-ascii" if len(name) > 10 else name,
)
def test_provider_names_made_of_visible_ascii_load(tmp_path: Path, name: str) -> None:
    data = table_file(providers=mock_providers(name), routes={"fast": [{"provider": name}]})
    table = Settings.from_env(env(write_json(tmp_path, data))).route_table
    assert list(table.providers) == [name]
    assert table.routes["fast"][0].provider == name


def test_every_visible_ascii_character_is_in_the_tested_range() -> None:
    assert len(EVERY_VISIBLE_ASCII) == 94
    assert EVERY_VISIBLE_ASCII[0] == "!"
    assert EVERY_VISIBLE_ASCII[-1] == "~"


def test_a_json_escaped_name_is_judged_after_decoding(tmp_path: Path) -> None:
    def text_for(name_literal: str) -> str:
        return f'{{"providers": {{"{name_literal}": {{"type": "mock"}}}}, "routes": {{}}}}'

    # Raw strings: the file holds a backslash escape, which the JSON parser decodes.
    table = Settings.from_env(env(write_text(tmp_path, text_for(r"\u0041bc")))).route_table
    assert list(table.providers) == ["Abc"]
    for literal in (r"a\u0020b", r"\u007f", r"a\u00e9", r"a\ud800", r"a\u000ab"):
        error = error_for(env(write_text(tmp_path, text_for(literal))))
        assert str(error) == f"{VAR}: providers: {NAME_REASON}"


def test_aliases_are_not_restricted_to_visible_ascii(tmp_path: Path) -> None:
    data = table_file(routes={"fast model \xe9": [{"provider": "m"}]})
    table = Settings.from_env(env(write_json(tmp_path, data))).route_table
    assert list(table.routes) == ["fast model \xe9"]


def test_create_app_stops_at_startup_on_a_bad_provider_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = table_file(providers=mock_providers("bad name"), routes={})
    for name, value in env(write_json(tmp_path, data)).items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError) as raised:
        create_app()
    assert str(raised.value) == f"{VAR}: providers: {NAME_REASON}"


@pytest.mark.parametrize(
    "name",
    [EVERY_VISIBLE_ASCII, "!", "~", "Mixed-Case_Name%41"],
    ids=["every-visible-ascii", "lowest", "highest", "mixed-case"],
)
def test_a_provider_name_is_served_unchanged_in_the_provider_header(
    tmp_path: Path, name: str
) -> None:
    data = table_file(providers=mock_providers(name), routes={"fast": [{"provider": name}]})
    settings = Settings.from_env(
        env(
            write_json(tmp_path, data),
            TOLLGATE_API_KEYS=AUTH_HEADERS["Authorization"].removeprefix("Bearer "),
            TOLLGATE_TOKENS_PER_MINUTE="600",
            TOLLGATE_CAPACITY_TOKENS="1000",
        )
    )
    body = {"model": "fast", "messages": [{"role": "user", "content": "hello there world"}]}
    with TestClient(create_app(settings, FakeClock())) as client:
        response = client.post(CHAT_URL, json=body, headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert (b"x-tollgate-provider", name.encode("ascii")) in response.headers.raw
    assert response.headers["x-tollgate-fallbacks"] == "0"
