"""How the three HTTP adapters use the shared code (T-210).

Each adapter forwards the reply's own status to its translation, and none repeats the request
handling or the reply checks that `post_json` and `fields` hold. Every test runs the provider on an
`httpx.MockTransport`: no network, no sleeping.
"""

import ast
import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.api.models import ChatMessage, ChatRequest, ChatResponse
from app.providers.anthropic import AnthropicProvider
from app.providers.base import Provider
from app.providers.errors import ProviderError
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider
from tests.fakes import FakeClock, FixedIdSource

REPLY_STATUS = 201
PROVIDERS_DIR = Path(__file__).resolve().parents[1] / "app" / "providers"
ADAPTER_FILES = ["ollama.py", "openai.py", "anthropic.py"]

Build = Callable[[httpx.AsyncClient], Provider]

BUILDERS: dict[str, Build] = {
    "ollama": lambda client: OllamaProvider(client, FakeClock(1000.0), FixedIdSource("id-1")),
    "openai": lambda client: OpenAIProvider(client, SecretStr("test-key")),
    "anthropic": lambda client: AnthropicProvider(
        client, SecretStr("test-key"), 256, FakeClock(1000.0), FixedIdSource("id-1")
    ),
}

# The smallest reply each adapter accepts.
VALID: dict[str, dict[str, Any]] = {
    "ollama": {
        "model": "m",
        "message": {"role": "assistant", "content": "hi"},
        "done_reason": "stop",
    },
    "openai": {
        "id": "chatcmpl-1",
        "created": 1,
        "model": "m",
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    },
    "anthropic": {
        "model": "m",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": 1, "output_tokens": 2},
    },
}

# Valid JSON that the adapter cannot translate: nothing in it, and a finish reason it does not map.
UNTRANSLATABLE: dict[str, list[dict[str, Any]]] = {
    "ollama": [{}, {**VALID["ollama"], "done_reason": "load"}],
    "openai": [
        {},
        {
            **VALID["openai"],
            "choices": [{"message": {"content": "hi"}, "finish_reason": "tool_calls"}],
        },
    ],
    "anthropic": [{}, {**VALID["anthropic"], "stop_reason": "tool_use"}],
}


def complete(name: str, body: dict[str, Any], status: int) -> ChatResponse | ProviderError:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
        base_url="http://provider.test",
    )
    provider = BUILDERS[name](client)
    request = ChatRequest(model="m", messages=[ChatMessage(role="user", content="hello")])

    async def go() -> ChatResponse | ProviderError:
        try:
            return await provider.complete(request)
        except ProviderError as error:
            return error
        finally:
            await client.aclose()

    return asyncio.run(go())


@pytest.mark.parametrize("name", list(BUILDERS))
def test_a_valid_201_reply_is_translated(name: str) -> None:
    # The control for the next test: these minimal bodies are valid, so that test fails for its
    # own reason and not because of a mistake in the body.
    result = complete(name, VALID[name], REPLY_STATUS)
    assert isinstance(result, ChatResponse), result
    assert result.choices[0].message.content == "hi"


@pytest.mark.parametrize("name", list(BUILDERS))
@pytest.mark.parametrize("index", [0, 1], ids=["empty-object", "unknown-finish-reason"])
def test_a_201_reply_that_cannot_be_translated_is_a_bad_response_with_status_201(
    name: str, index: int
) -> None:
    result = complete(name, UNTRANSLATABLE[name][index], REPLY_STATUS)
    assert isinstance(result, ProviderError), result
    assert (result.kind, result.status_code, result.retryable) == (
        "bad_response",
        REPLY_STATUS,
        False,
    )


# The adapters hold no copy of the shared code.

FORBIDDEN_FUNCTIONS = {
    "_text",
    "_non_empty_text",
    "_whole_number",
    "_required_count",
    "_status_error",
}
FORBIDDEN_NAME = "RATE_LIMITED_STATUS"
REQUIRED_MODULE = "app.providers.http_body"
REQUIRED_NAME = "post_json"


def violations(source: str) -> list[str]:
    """What in an adapter's source repeats the shared code, or is missing from it."""
    found: list[str] = []
    imports_post_json = False
    calls_post_json = False
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Try | ast.TryStar):
            found.append(f"try at line {node.lineno}")
        elif isinstance(node, ast.Import):
            found += [
                f"import {alias.name}"
                for alias in node.names
                if alias.name == "json" or alias.name.startswith("json.")
            ]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "json" or module.startswith("json."):
                found.append(f"from {module} import")
            if module == REQUIRED_MODULE and any(a.name == REQUIRED_NAME for a in node.names):
                imports_post_json = True
            found += [
                f"import of {FORBIDDEN_NAME}"
                for alias in node.names
                if FORBIDDEN_NAME in (alias.name, alias.asname)
            ]
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in FORBIDDEN_FUNCTIONS:
                found.append(f"def {node.name}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == REQUIRED_NAME:
                calls_post_json = True
        elif isinstance(node, ast.Name) and node.id == FORBIDDEN_NAME:
            found.append(f"name {FORBIDDEN_NAME}")
        elif isinstance(node, ast.Attribute) and node.attr == FORBIDDEN_NAME:
            found.append(f"attribute {FORBIDDEN_NAME}")
    if not imports_post_json:
        found.append("no import of post_json")
    if not calls_post_json:
        found.append("no call of post_json")
    return found


@pytest.mark.parametrize("file_name", ADAPTER_FILES)
def test_an_adapter_holds_no_copy_of_the_shared_code(file_name: str) -> None:
    source = (PROVIDERS_DIR / file_name).read_text(encoding="utf-8")
    assert violations(source) == []


# One line, so the line numbers in the cases below do not move.
IMPORT_POST_JSON = "from app.providers.http_body import post_json; post_json()\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(IMPORT_POST_JSON + "x = 1\n", [], id="clean"),
        pytest.param(IMPORT_POST_JSON + "import jsonschema\n", [], id="lookalike-module"),
        pytest.param(
            IMPORT_POST_JSON + "def text(): ...\n", [], id="shared-name-without-underscore"
        ),
        pytest.param(
            "from app.providers.http_body import read_capped, post_json\npost_json()\n",
            [],
            id="post-json-imported-after-another-name",
        ),
        pytest.param(
            "x = 1\n", ["no import of post_json", "no call of post_json"], id="no-post-json"
        ),
        pytest.param(
            "from app.providers.http_body import read_capped\n",
            ["no import of post_json", "no call of post_json"],
            id="other-http-body-import",
        ),
        pytest.param(
            "from app.providers.http_body import post_json\n",
            ["no call of post_json"],
            id="post-json-imported-and-never-called",
        ),
        pytest.param(
            "from app.providers.http_body import post_json as pj\npj()\n",
            ["no call of post_json"],
            id="post-json-aliased",
        ),
        pytest.param(
            "from other.module import post_json\npost_json()\n",
            ["no import of post_json"],
            id="post-json-from-another-module",
        ),
        pytest.param(
            IMPORT_POST_JSON + "try:\n    pass\nexcept ValueError:\n    pass\n",
            ["try at line 2"],
            id="try",
        ),
        pytest.param(
            IMPORT_POST_JSON + "def f():\n    try:\n        pass\n    finally:\n        pass\n",
            ["try at line 3"],
            id="try-finally-in-a-function",
        ),
        pytest.param(
            IMPORT_POST_JSON + "try:\n    pass\nexcept* ValueError:\n    pass\n",
            ["try at line 2"],
            id="try-star",
        ),
        pytest.param(IMPORT_POST_JSON + "import json\n", ["import json"], id="import-json"),
        pytest.param(
            IMPORT_POST_JSON + "import json.decoder\n",
            ["import json.decoder"],
            id="import-json-sub",
        ),
        pytest.param(
            IMPORT_POST_JSON + "import json as j\n", ["import json"], id="import-json-aliased"
        ),
        pytest.param(
            IMPORT_POST_JSON + "from json import loads\n", ["from json import"], id="from-json"
        ),
        pytest.param(
            IMPORT_POST_JSON + "from json.decoder import JSONDecodeError\n",
            ["from json.decoder import"],
            id="from-json-sub",
        ),
        pytest.param(IMPORT_POST_JSON + "def _text(): ...\n", ["def _text"], id="def-text"),
        pytest.param(
            IMPORT_POST_JSON + "def _non_empty_text(): ...\n",
            ["def _non_empty_text"],
            id="def-non-empty-text",
        ),
        pytest.param(
            IMPORT_POST_JSON + "def _whole_number(): ...\n",
            ["def _whole_number"],
            id="def-whole-number",
        ),
        pytest.param(
            IMPORT_POST_JSON + "def _required_count(): ...\n",
            ["def _required_count"],
            id="def-required-count",
        ),
        pytest.param(
            IMPORT_POST_JSON + "def _status_error(): ...\n",
            ["def _status_error"],
            id="def-status-error",
        ),
        pytest.param(
            IMPORT_POST_JSON + "async def _status_error(): ...\n",
            ["def _status_error"],
            id="async-def-status-error",
        ),
        pytest.param(
            IMPORT_POST_JSON + "RATE_LIMITED_STATUS = 429\n",
            ["name RATE_LIMITED_STATUS"],
            id="assign-rate-limited-status",
        ),
        pytest.param(
            IMPORT_POST_JSON + "x = RATE_LIMITED_STATUS\n",
            ["name RATE_LIMITED_STATUS"],
            id="use-rate-limited-status",
        ),
        pytest.param(
            IMPORT_POST_JSON + "x = http_body.RATE_LIMITED_STATUS\n",
            ["attribute RATE_LIMITED_STATUS"],
            id="attribute-rate-limited-status",
        ),
        pytest.param(
            IMPORT_POST_JSON + "from app.providers.http_body import RATE_LIMITED_STATUS\n",
            ["import of RATE_LIMITED_STATUS"],
            id="import-rate-limited-status",
        ),
    ],
)
def test_the_source_scanner_flags_each_forbidden_construct(
    source: str, expected: list[str]
) -> None:
    assert violations(source) == expected
