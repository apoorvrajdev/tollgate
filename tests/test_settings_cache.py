"""The cache settings (ADR-0014, ADR-0015, T-302): rules, boundaries and error text."""

import dataclasses

import pytest

from app.settings import CacheSettings, Settings, SettingsError

EMBEDDER = "TOLLGATE_CACHE_EMBEDDER"
MODEL = "TOLLGATE_CACHE_EMBEDDER_MODEL"
URL = "TOLLGATE_CACHE_EMBEDDER_URL"
THRESHOLD = "TOLLGATE_CACHE_SIMILARITY_THRESHOLD"
TTL = "TOLLGATE_CACHE_TTL_SECONDS"
MAX = "TOLLGATE_CACHE_MAX_ENTRIES"
DEPENDENT = [MODEL, URL, THRESHOLD, TTL, MAX]
SENTINEL = "SENTINEL-value-3d9a"
URL_PASSWORD = "url-pw-sentinel-6e1f"
VALID = {"TOLLGATE_API_KEYS": "k1", "TOLLGATE_TOKENS_PER_MINUTE": "60"}
CACHE = {EMBEDDER: "ollama", MODEL: "all-minilm", THRESHOLD: "0.9"}


def load(**overrides: str) -> CacheSettings:
    cache = Settings.from_env({**VALID, **CACHE, **overrides}).cache
    assert cache is not None
    return cache


def error_for(environ: dict[str, str]) -> SettingsError:
    with pytest.raises(SettingsError) as info:
        Settings.from_env({**VALID, **environ})
    return info.value


def cache_error(**overrides: str) -> SettingsError:
    return error_for({**CACHE, **overrides})


def assert_names(error: SettingsError, variable: str) -> None:
    assert error.variable == variable
    assert str(error).startswith(f"{variable}: ")
    assert error.__context__ is None


def test_cache_is_none_when_the_embedder_is_unset_and_no_cache_variable_is_set() -> None:
    assert Settings.from_env(VALID).cache is None
    # A name outside the five is not a cache variable.
    assert Settings.from_env({**VALID, "TOLLGATE_CACHE_UNKNOWN": "x"}).cache is None


def test_a_complete_valid_set_loads_the_exact_values() -> None:
    cache = load(
        **{MODEL: "  bge-m3  ", URL: " http://h:1 ", THRESHOLD: "0.8750", TTL: "120", MAX: "50"}
    )
    assert cache.embedder == "ollama"
    assert cache.embedder_model == "bge-m3"
    assert cache.embedder_url.get_secret_value() == "http://h:1"
    assert cache.similarity_threshold == 0.875
    assert type(cache.similarity_threshold) is float
    assert (cache.ttl_seconds, cache.max_entries) == (120, 50)


def test_the_defaults_apply_to_each_optional_variable_on_its_own() -> None:
    cache = load()
    assert cache.embedder_url.get_secret_value() == "http://localhost:11434"
    assert (cache.ttl_seconds, cache.max_entries) == (3_600, 1_000)
    assert load(**{TTL: "61"}).max_entries == 1_000
    assert load(**{MAX: "7"}).ttl_seconds == 3_600


@pytest.mark.parametrize(
    "value", ["redis", "Ollama", "OLLAMA", " ollama", "ollama\n", "", " "], ids=repr
)
def test_the_embedder_must_be_exactly_ollama(value: str) -> None:
    assert_names(cache_error(**{EMBEDDER: value}), EMBEDDER)


@pytest.mark.parametrize("value", ["", " ", "\t\n"], ids=repr)
def test_a_blank_model_is_an_error_and_an_unset_one_too(value: str) -> None:
    assert_names(cache_error(**{MODEL: value}), MODEL)
    environ = {key: val for key, val in CACHE.items() if key != MODEL}
    assert_names(error_for(environ), MODEL)


@pytest.mark.parametrize("value", ["", " ", "\t"], ids=repr)
def test_a_blank_url_is_an_error_and_never_the_default(value: str) -> None:
    assert_names(cache_error(**{URL: value}), URL)


ACCEPTED_THRESHOLDS = [
    ("0.5", 0.5),
    ("0.50", 0.5),
    ("0.5000", 0.5),
    ("0.9999", 0.9999),
    ("0.75", 0.75),
    ("1", 1.0),
    ("1.0", 1.0),
    ("1.0000", 1.0),
    (" 0.9 ", 0.9),
]


@pytest.mark.parametrize(
    ("text", "value"), ACCEPTED_THRESHOLDS, ids=[t for t, _ in ACCEPTED_THRESHOLDS]
)
def test_a_threshold_inside_the_range_is_accepted_exactly(text: str, value: float) -> None:
    assert load(**{THRESHOLD: text}).similarity_threshold == value


BAD_THRESHOLDS = [
    "",
    " ",
    "0.4999",
    "0.4",
    "0.0",
    "0",
    "0.",
    "1.0001",
    "1.00001",
    "1.1",
    "2",
    "1.",
    "01",
    "0.12345",
    "0.99999",
    ".9",
    "1e0",
    "9e-1",
    "-0.9",
    "+0.9",
    "0,9",
    "nan",
    "inf",
    "0x1",
    "0.9x",
    "0.9 5",
    "0.9\n0",
    "\uff10.\uff19",
    "0.\uff19",
    "0.\u0669",
]


@pytest.mark.parametrize("text", BAD_THRESHOLDS, ids=repr)
def test_a_threshold_outside_the_grammar_or_below_one_half_is_rejected(text: str) -> None:
    assert_names(cache_error(**{THRESHOLD: text}), THRESHOLD)


def test_an_unset_threshold_is_an_error() -> None:
    environ = {key: val for key, val in CACHE.items() if key != THRESHOLD}
    assert_names(error_for(environ), THRESHOLD)


BAD_COUNTS = ["abc", "", " ", "1.5", "-60", "1e3", "\uff16\uff10", "9" * 19, "9" * 5000]


@pytest.mark.parametrize(
    ("variable", "low", "high"), [(TTL, 60, 604_800), (MAX, 1, 100_000)], ids=["ttl", "max"]
)
def test_a_count_is_bounded_on_both_sides_and_blank_is_an_error(
    variable: str, low: int, high: int
) -> None:
    stored = "ttl_seconds" if variable == TTL else "max_entries"
    assert getattr(load(**{variable: str(low)}), stored) == low
    assert getattr(load(**{variable: str(high)}), stored) == high
    # leading zeros and surrounding spaces, as the other numbers
    assert getattr(load(**{variable: f" 0{low} "}), stored) == low
    for text in [str(low - 1), str(high + 1), *BAD_COUNTS]:
        assert_names(cache_error(**{variable: text}), variable)


def test_the_boundary_values_are_stored() -> None:
    low = load(**{TTL: "60", MAX: "1"})
    high = load(**{TTL: "604800", MAX: "100000"})
    assert (low.ttl_seconds, low.max_entries) == (60, 1)
    assert (high.ttl_seconds, high.max_entries) == (604_800, 100_000)


@pytest.mark.parametrize("name", DEPENDENT)
@pytest.mark.parametrize("value", ["1", "", "  "], ids=repr)
def test_a_cache_variable_without_the_embedder_is_an_error_naming_it(name: str, value: str) -> None:
    assert_names(error_for({name: value}), name)


def test_the_first_error_is_reported_in_declaration_order() -> None:
    assert_names(error_for({THRESHOLD: "0.9", TTL: "120"}), THRESHOLD)
    assert_names(error_for({TTL: "120", MODEL: "m"}), MODEL)
    assert_names(cache_error(**{THRESHOLD: "x", TTL: "x", MAX: "x"}), THRESHOLD)
    assert_names(cache_error(**{TTL: "x", MAX: "x"}), TTL)
    assert_names(cache_error(**{MODEL: " ", URL: " ", THRESHOLD: "x"}), MODEL)
    assert_names(cache_error(**{URL: " ", THRESHOLD: "x"}), URL)


def test_the_cache_is_checked_after_the_other_settings() -> None:
    with pytest.raises(SettingsError) as info:
        Settings.from_env({"TOLLGATE_TOKENS_PER_MINUTE": "60", **CACHE, THRESHOLD: "x"})
    assert info.value.variable == "TOLLGATE_API_KEYS"


def test_a_route_table_error_is_reported_before_a_cache_error() -> None:
    # A blank routes file is an error of its own; the cache's bad threshold comes second.
    error = cache_error(**{"TOLLGATE_ROUTES_FILE": "", THRESHOLD: "x"})
    assert error.variable == "TOLLGATE_ROUTES_FILE"


@pytest.mark.parametrize("name", [EMBEDDER, THRESHOLD, TTL, MAX])
def test_an_error_names_the_variable_and_never_shows_the_value(name: str) -> None:
    # The model and the URL accept any text, so no value of theirs can be rejected and shown.
    error = error_for({**CACHE, name: SENTINEL})
    assert SENTINEL not in str(error) + repr(error)


def test_the_url_is_masked_in_repr_and_not_in_an_error() -> None:
    url = f"http://user:{URL_PASSWORD}@ollama.test:11434"
    settings = Settings.from_env({**VALID, **CACHE, URL: url})
    assert settings.cache is not None
    assert settings.cache.embedder_url.get_secret_value() == url
    assert URL_PASSWORD not in repr(settings) + repr(settings.cache)
    assert URL_PASSWORD not in str(cache_error(**{URL: url, THRESHOLD: "x"}))


def test_cache_settings_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        load().ttl_seconds = 1  # type: ignore[misc]
