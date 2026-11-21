"""The committed example route table (docs/routes.example.json) must load under the real schema."""

from pathlib import Path

from app.routing.config import AnthropicProviderConfig, OllamaProviderConfig, OpenAIProviderConfig
from app.settings import Settings

EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "routes.example.json"
PLACEHOLDER_ENV = {
    "TOLLGATE_API_KEYS": "placeholder-gateway-key",
    "TOLLGATE_TOKENS_PER_MINUTE": "60000",
    "TOLLGATE_ROUTES_FILE": str(EXAMPLE),
    "OPENAI_API_KEY": "placeholder-openai-value",
    "ANTHROPIC_API_KEY": "placeholder-anthropic-value",
}


def test_example_route_table_loads_with_placeholder_environment() -> None:
    table = Settings.from_env(PLACEHOLDER_ENV).route_table
    assert isinstance(table.providers["local"], OllamaProviderConfig)
    assert isinstance(table.providers["openai"], OpenAIProviderConfig)
    assert isinstance(table.providers["claude"], AnthropicProviderConfig)
    assert [t.provider for t in table.routes["fast"]] == ["local", "openai"]
    assert [t.provider for t in table.routes["smart"]] == ["claude", "openai"]
    assert table.default is not None
    assert [t.provider for t in table.default] == ["local"]
    assert set(table.api_keys) == {"openai", "claude"}
    assert table.api_keys["openai"].get_secret_value() == "placeholder-openai-value"
    assert table.api_keys["claude"].get_secret_value() == "placeholder-anthropic-value"
