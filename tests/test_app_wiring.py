import pytest

import app.main
from app.clock import SystemClock
from app.main import create_app
from app.settings import SettingsError
from tests.fakes import FakeClock, make_settings


def test_create_app_without_arguments_reads_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOLLGATE_API_KEYS", "env-key")
    monkeypatch.setenv("TOLLGATE_TOKENS_PER_MINUTE", "777")
    application = create_app()
    assert application.state.settings.tokens_per_minute == 777


def test_create_app_without_arguments_fails_naming_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TOLLGATE_API_KEYS",
        "TOLLGATE_TOKENS_PER_MINUTE",
        "TOLLGATE_CAPACITY_TOKENS",
        "TOLLGATE_LIMITER_BACKEND",
        "TOLLGATE_REDIS_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SettingsError, match="TOLLGATE_API_KEYS"):
        create_app()


def test_create_app_uses_injected_settings_and_clock_ignoring_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOLLGATE_API_KEYS", "")
    monkeypatch.setenv("TOLLGATE_TOKENS_PER_MINUTE", "not-a-number")
    settings = make_settings()
    clock = FakeClock()
    application = create_app(settings, clock)
    assert application.state.settings is settings
    assert application.state.clock is clock


def test_create_app_defaults_to_system_clock() -> None:
    assert isinstance(create_app(make_settings()).state.clock, SystemClock)


def test_app_main_has_no_module_level_app() -> None:
    assert not hasattr(app.main, "app")
