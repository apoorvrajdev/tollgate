import pytest

from app.settings import METRICS_TOKEN_VAR, Settings, SettingsError

TOKEN_32 = "m" * 32
SENTINEL_TOKEN = "SENTINEL-metrics-token-9d41c7e2b8a6f0"
VALID = {"TOLLGATE_API_KEYS": "k1, k2", "TOLLGATE_TOKENS_PER_MINUTE": "60"}


def settings_with(token: str | None, **extra: str) -> Settings:
    environ = {**VALID, **extra}
    if token is not None:
        environ[METRICS_TOKEN_VAR] = token
    return Settings.from_env(environ)


def error_for(token: str, **extra: str) -> SettingsError:
    with pytest.raises(SettingsError) as info:
        settings_with(token, **extra)
    return info.value


def test_an_unset_token_is_none() -> None:
    assert settings_with(None).metrics_token is None


@pytest.mark.parametrize("token", ["", " ", "     ", "\t"])
def test_a_blank_token_is_rejected_and_names_the_variable(token: str) -> None:
    error = error_for(token)
    assert error.variable == METRICS_TOKEN_VAR
    assert str(error) == f"{METRICS_TOKEN_VAR}: must not be blank"


def test_31_characters_are_rejected_and_32_and_33_are_accepted() -> None:
    error = error_for("m" * 31)
    assert str(error) == f"{METRICS_TOKEN_VAR}: must be at least 32 characters"
    for token in (TOKEN_32, "m" * 33):
        stored = settings_with(token).metrics_token
        assert stored is not None
        assert stored.get_secret_value() == token


def test_length_counts_characters_not_bytes() -> None:
    token = "é" * 32  # 32 characters, 64 bytes
    stored = settings_with(token).metrics_token
    assert stored is not None
    assert stored.get_secret_value() == token
    assert error_for("é" * 31).variable == METRICS_TOKEN_VAR


def test_surrounding_spaces_are_trimmed_before_the_length_check() -> None:
    stored = settings_with(f"  {TOKEN_32}  ").metrics_token
    assert stored is not None
    assert stored.get_secret_value() == TOKEN_32
    assert error_for(f"  {'m' * 31}  ").variable == METRICS_TOKEN_VAR


def test_a_token_equal_to_any_api_key_is_rejected() -> None:
    first, second = "f" * 40, "s" * 40
    for key_list, token in (
        (f"{first},{second}", first),
        (f"{first},{second}", second),
        (f"{first},{second}", f"  {second}  "),
    ):
        error = error_for(token, TOLLGATE_API_KEYS=key_list)
        assert str(error) == f"{METRICS_TOKEN_VAR}: must differ from every API key"


def test_a_long_token_that_only_resembles_a_key_is_accepted() -> None:
    key = "k" * 40
    assert settings_with(key + "x", TOLLGATE_API_KEYS=key).metrics_token is not None
    assert settings_with(key.upper(), TOLLGATE_API_KEYS=key).metrics_token is not None


def test_errors_never_show_the_token_or_a_key() -> None:
    key = "KEY-" + "z" * 40
    for token, extra in (
        (SENTINEL_TOKEN[:20], {}),
        (key, {"TOLLGATE_API_KEYS": key}),
    ):
        error = error_for(token, **extra)
        shown = f"{error!s} {error!r} {error.args}"
        assert token not in shown
        assert key not in shown


def test_the_token_is_a_secretstr_and_hidden_in_repr() -> None:
    settings = settings_with(SENTINEL_TOKEN)
    assert SENTINEL_TOKEN not in repr(settings)
    assert SENTINEL_TOKEN not in str(settings)
    assert settings.metrics_token is not None
    assert settings.metrics_token.get_secret_value() == SENTINEL_TOKEN
