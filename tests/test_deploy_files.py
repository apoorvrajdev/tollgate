"""The deployment files stay consistent with each other and with the settings (ADR-0017)."""

import re
from pathlib import Path

from app.routing.config import MockProviderConfig, OpenAIProviderConfig
from app.settings import Settings
from tests.fakes import load_script

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
COMPOSE_ROUTES = ROOT / "deploy" / "routes.compose.json"
BENCH_FAKE_ROUTES = ROOT / "deploy" / "bench" / "routes.fake-upstream.json"
BENCH_MOCK_ROUTES = ROOT / "deploy" / "bench" / "routes.mock.json"
fake = load_script("fake_upstream")
PLACEHOLDER_ENV = {
    "TOLLGATE_API_KEYS": "placeholder-gateway-key",
    "TOLLGATE_TOKENS_PER_MINUTE": "60000",
}
REDIS_IMAGE = re.compile(r"^\s*image:\s*(redis:\S+)\s*$", re.MULTILINE)
FROM_LINE = re.compile(r"^FROM\s+(\S+)", re.MULTILINE | re.IGNORECASE)
DIGEST_REF = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
SECRET_VARS = ("TOLLGATE_API_KEYS", "TOLLGATE_METRICS_TOKEN")


def test_compose_route_table_loads_with_the_mock_provider_only() -> None:
    environ = {
        "TOLLGATE_API_KEYS": "placeholder-gateway-key",
        "TOLLGATE_TOKENS_PER_MINUTE": "60000",
        "TOLLGATE_ROUTES_FILE": str(COMPOSE_ROUTES),
    }
    table = Settings.from_env(environ).route_table
    assert set(table.providers) == {"mock"}
    assert isinstance(table.providers["mock"], MockProviderConfig)
    assert table.api_keys == {}
    assert table.default is not None
    assert [t.provider for t in table.default] == ["mock"]


def test_bench_fake_upstream_route_table_loads_with_one_openai_provider_at_the_fake() -> None:
    environ = {
        **PLACEHOLDER_ENV,
        "TOLLGATE_ROUTES_FILE": str(BENCH_FAKE_ROUTES),
        "TOLLGATE_BENCH_UPSTREAM_KEY": "placeholder-upstream-key",
    }
    table = Settings.from_env(environ).route_table
    assert set(table.providers) == {"fake-upstream"}
    provider = table.providers["fake-upstream"]
    assert isinstance(provider, OpenAIProviderConfig)
    assert provider.base_url == f"http://{fake.DEFAULT_HOST}:{fake.DEFAULT_PORT}"
    assert table.api_keys["fake-upstream"].get_secret_value() == "placeholder-upstream-key"
    assert table.default is not None
    assert [t.provider for t in table.default] == ["fake-upstream"]


def test_bench_mock_route_table_loads_with_the_mock_provider_only() -> None:
    environ = {**PLACEHOLDER_ENV, "TOLLGATE_ROUTES_FILE": str(BENCH_MOCK_ROUTES)}
    table = Settings.from_env(environ).route_table
    assert set(table.providers) == {"mock"}
    assert isinstance(table.providers["mock"], MockProviderConfig)
    assert table.api_keys == {}
    assert table.default is not None
    assert [t.provider for t in table.default] == ["mock"]


def test_redis_tag_in_compose_equals_the_tag_in_ci() -> None:
    compose_tags = REDIS_IMAGE.findall(COMPOSE.read_text(encoding="utf-8"))
    ci_tags = REDIS_IMAGE.findall(CI.read_text(encoding="utf-8"))
    assert len(compose_tags) == 1
    assert len(ci_tags) == 1
    assert compose_tags == ci_tags
    assert compose_tags[0] != "redis:latest"


def test_every_from_line_carries_a_digest() -> None:
    images = FROM_LINE.findall(DOCKERFILE.read_text(encoding="utf-8"))
    assert len(images) == 2
    for image in images:
        assert DIGEST_REF.match(image), image


def test_compose_takes_the_key_and_the_token_only_as_required_references() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    for name in SECRET_VARS:
        lines = [line.strip() for line in text.splitlines() if line.strip().startswith(f"{name}:")]
        assert len(lines) == 1, name
        value = lines[0].split(":", 1)[1].strip()
        assert re.fullmatch(r"\$\{" + name + r":\?[^}]+\}", value), lines[0]
