import dataclasses

import pytest

from app.settings import Settings, SettingsError
from tests.fakes import make_settings

SENTINEL = "sk-sentinel-7f3a9c"
REDIS_PASSWORD = "redis-pw-sentinel-1b2c"
VALID = {"TOLLGATE_API_KEYS": "k1", "TOLLGATE_TOKENS_PER_MINUTE": "60"}

BAD_NUMBERS = [
    "9" * 5000,
    "9" * 19,
    "abc",
    "1.5",
    "0",
    "-1",
    "",
    " ",
    "1e3",
    "1_000",
    "+5",
    "\uff11\uff10",
    "0x10",
    "00",
]


def key_values(settings: Settings) -> tuple[str, ...]:
    return tuple(key.get_secret_value() for key in settings.api_keys)


def error_for(environ: dict[str, str]) -> SettingsError:
    with pytest.raises(SettingsError) as info:
        Settings.from_env(environ)
    return info.value


def test_settings_defaults_backend_memory_and_capacity_equals_rate() -> None:
    settings = Settings.from_env(VALID)
    assert settings.limiter_backend == "memory"
    assert settings.capacity_tokens == 60
    assert settings.tokens_per_minute == 60
    assert settings.redis_url is None


def test_settings_explicit_capacity_overrides_default() -> None:
    settings = Settings.from_env({**VALID, "TOLLGATE_CAPACITY_TOKENS": "500"})
    assert settings.capacity_tokens == 500
    assert settings.tokens_per_minute == 60


def test_settings_explicit_redis_backend_with_url() -> None:
    settings = Settings.from_env(
        {**VALID, "TOLLGATE_LIMITER_BACKEND": "redis", "TOLLGATE_REDIS_URL": "redis://host:6379/0"}
    )
    assert settings.limiter_backend == "redis"
    assert settings.redis_url is not None
    assert settings.redis_url.get_secret_value() == "redis://host:6379/0"


def test_settings_parses_keys_trimming_whitespace_in_order() -> None:
    settings = Settings.from_env({**VALID, "TOLLGATE_API_KEYS": " a , b,c "})
    assert key_values(settings) == ("a", "b", "c")


def test_settings_accepts_one_token_per_minute() -> None:
    settings = Settings.from_env({**VALID, "TOLLGATE_TOKENS_PER_MINUTE": "1"})
    assert settings.tokens_per_minute == 1


def test_settings_trims_whitespace_around_numbers() -> None:
    settings = Settings.from_env({**VALID, "TOLLGATE_TOKENS_PER_MINUTE": " 42 "})
    assert settings.tokens_per_minute == 42


@pytest.mark.parametrize("keys", [None, "", "  "])
def test_settings_rejects_missing_or_blank_keys(keys: str | None) -> None:
    environ = {"TOLLGATE_TOKENS_PER_MINUTE": "60"}
    if keys is not None:
        environ["TOLLGATE_API_KEYS"] = keys
    error = error_for(environ)
    assert error.variable == "TOLLGATE_API_KEYS"
    assert "at least one key" in str(error)


@pytest.mark.parametrize("keys", [",", "a,,b", "a,", ",a", "a, ,b"])
def test_settings_rejects_empty_key_piece(keys: str) -> None:
    error = error_for({**VALID, "TOLLGATE_API_KEYS": keys})
    assert str(error).startswith("TOLLGATE_API_KEYS:")
    assert "empty key" in str(error)


def test_settings_rejects_unset_tokens_per_minute() -> None:
    assert error_for({"TOLLGATE_API_KEYS": "k"}).variable == "TOLLGATE_TOKENS_PER_MINUTE"


@pytest.mark.parametrize("number", BAD_NUMBERS)
def test_settings_rejects_bad_tokens_per_minute(number: str) -> None:
    error = error_for({**VALID, "TOLLGATE_TOKENS_PER_MINUTE": number})
    assert str(error).startswith("TOLLGATE_TOKENS_PER_MINUTE:")


@pytest.mark.parametrize("number", BAD_NUMBERS)
def test_settings_rejects_bad_capacity_naming_capacity_variable(number: str) -> None:
    error = error_for({**VALID, "TOLLGATE_CAPACITY_TOKENS": number})
    assert str(error).startswith("TOLLGATE_CAPACITY_TOKENS:")
    assert "PER_MINUTE" not in str(error)


@pytest.mark.parametrize("backend", ["postgres", "REDIS", "Redis", "", " memory"])
def test_settings_rejects_unknown_backend(backend: str) -> None:
    error = error_for({**VALID, "TOLLGATE_LIMITER_BACKEND": backend})
    assert str(error).startswith("TOLLGATE_LIMITER_BACKEND:")


@pytest.mark.parametrize("url", [None, "", " "])
def test_settings_rejects_redis_without_url(url: str | None) -> None:
    environ = {**VALID, "TOLLGATE_LIMITER_BACKEND": "redis"}
    if url is not None:
        environ["TOLLGATE_REDIS_URL"] = url
    assert error_for(environ).variable == "TOLLGATE_REDIS_URL"


def test_settings_memory_backend_does_not_require_url() -> None:
    assert Settings.from_env({**VALID, "TOLLGATE_LIMITER_BACKEND": "memory"}).redis_url is None


def test_repr_and_str_never_contain_key_or_redis_password() -> None:
    settings = Settings.from_env(
        {
            "TOLLGATE_API_KEYS": f"{SENTINEL},other-{SENTINEL}",
            "TOLLGATE_TOKENS_PER_MINUTE": "60",
            "TOLLGATE_LIMITER_BACKEND": "redis",
            "TOLLGATE_REDIS_URL": f"redis://user:{REDIS_PASSWORD}@host:6379/0",
        }
    )
    for text in (repr(settings), str(settings)):
        assert SENTINEL not in text
        assert REDIS_PASSWORD not in text
    assert key_values(settings)[0] == SENTINEL


@pytest.mark.parametrize(
    "overrides",
    [
        {"TOLLGATE_TOKENS_PER_MINUTE": f"{SENTINEL}"},
        {"TOLLGATE_API_KEYS": f"{SENTINEL},,x"},
        {"TOLLGATE_LIMITER_BACKEND": SENTINEL},
        {"TOLLGATE_CAPACITY_TOKENS": SENTINEL},
        {"TOLLGATE_LIMITER_BACKEND": "redis", "TOLLGATE_REDIS_URL": " "},
    ],
)
def test_error_messages_never_contain_sentinel(overrides: dict[str, str]) -> None:
    environ = {"TOLLGATE_API_KEYS": SENTINEL, "TOLLGATE_TOKENS_PER_MINUTE": "60", **overrides}
    assert SENTINEL not in str(error_for(environ))


def test_settings_is_frozen() -> None:
    settings = make_settings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.tokens_per_minute = 5  # type: ignore[misc]


def test_from_env_reads_only_given_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOLLGATE_API_KEYS", "from-os")
    monkeypatch.setenv("TOLLGATE_TOKENS_PER_MINUTE", "999")
    settings = Settings.from_env(VALID)
    assert key_values(settings) == ("k1",)
    assert settings.tokens_per_minute == 60
