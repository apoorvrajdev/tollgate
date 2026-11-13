from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.models import ChatRequest, ChatResponse
from app.main import create_app
from app.providers.mock import MockProvider
from tests.fakes import AUTH_HEADERS, FakeClock, FixedIdSource, make_settings

URL = "/v1/chat/completions"
CREATED_SECONDS = 1_700_000_000
RESPONSE_ID = "chatcmpl-test"

# Fields that the OpenAI Python SDK types require when parsing a chat completion, per level.
# Source: openai-python main, src/openai/types/chat/chat_completion.py and
# chat_completion_message.py, and src/openai/types/completion_usage.py, read on 2026-11-13.
# The openai-openapi spec also lists choices[].logprobs and message.content/refusal as required
# but nullable; the SDK defaults them to None, and this gateway leaves them out (ADR-0008 scope).
OPENAI_REQUIRED_RESPONSE_FIELDS = {
    "response": {"id", "choices", "created", "model", "object"},
    "choice": {"finish_reason", "index", "message"},
    "message": {"role"},
    "usage": {"prompt_tokens", "completion_tokens", "total_tokens"},
}


def make_client() -> TestClient:
    clock = FakeClock(CREATED_SECONDS)
    provider = MockProvider(clock, FixedIdSource(RESPONSE_ID))
    return TestClient(create_app(make_settings(), clock, provider=provider), headers=AUTH_HEADERS)


def valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "mock-1",
        "messages": [{"role": "user", "content": "hello there world"}],
    }
    payload.update(overrides)
    return payload


def test_valid_request_returns_200_with_the_exact_expected_body() -> None:
    response = make_client().post(URL, json=valid_payload())
    assert response.status_code == 200
    assert response.json() == {
        "id": RESPONSE_ID,
        "object": "chat.completion",
        "created": CREATED_SECONDS,
        "model": "mock-1",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Mock reply: hello there world"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
    }


def test_response_has_every_field_the_openai_sdk_requires() -> None:
    body = make_client().post(URL, json=valid_payload()).json()
    required = OPENAI_REQUIRED_RESPONSE_FIELDS
    assert required["response"] <= set(body)
    assert required["choice"] <= set(body["choices"][0])
    assert required["message"] <= set(body["choices"][0]["message"])
    assert required["usage"] <= set(body["usage"])


def test_response_body_parses_back_into_the_response_model() -> None:
    body = make_client().post(URL, json=valid_payload()).json()
    assert ChatResponse.model_validate(body).object == "chat.completion"


def test_identical_requests_return_identical_bodies() -> None:
    client = make_client()
    first = client.post(URL, json=valid_payload()).json()
    second = client.post(URL, json=valid_payload()).json()
    assert first == second


def test_response_content_type_is_json() -> None:
    response = make_client().post(URL, json=valid_payload())
    assert response.headers["content-type"] == "application/json"


REJECTIONS: list[tuple[str, dict[str, Any], str | None, str]] = [
    ("missing model", {"model": None}, "model", "missing_required_parameter"),
    ("empty messages", {"messages": []}, "messages", "invalid_value"),
    (
        "unknown role",
        {"messages": [{"role": "robot", "content": "x"}]},
        "messages[0].role",
        "invalid_value",
    ),
    ("temperature 3", {"temperature": 3}, "temperature", "invalid_value"),
    ("n 2", {"n": 2}, "n", "unsupported_parameter"),
    (
        "array content",
        {"messages": [{"role": "user", "content": [{"type": "text", "text": "x"}]}]},
        "messages[0].content",
        "unsupported_parameter",
    ),
    ("stream true", {"stream": True}, "stream", "unsupported_parameter"),
]


def rejection_payload(overrides: dict[str, Any]) -> dict[str, Any]:
    payload = valid_payload(**overrides)
    return {key: value for key, value in payload.items() if value is not None}


@pytest.mark.parametrize(
    ("overrides", "param", "code"),
    [case[1:] for case in REJECTIONS],
    ids=[case[0] for case in REJECTIONS],
)
def test_each_rejection_returns_400_with_the_adr_0008_body(
    overrides: dict[str, Any], param: str, code: str
) -> None:
    response = make_client().post(URL, json=rejection_payload(overrides))
    assert response.status_code == 400
    error = response.json()["error"]
    assert set(error) == {"message", "type", "param", "code"}
    assert error["type"] == "invalid_request_error"
    assert (error["param"], error["code"]) == (param, code)


def test_stream_true_uses_the_code_and_param_fixed_by_adr_0008() -> None:
    error = make_client().post(URL, json=valid_payload(stream=True)).json()["error"]
    assert (error["code"], error["param"]) == ("unsupported_parameter", "stream")


def test_no_rejection_is_422() -> None:
    client = make_client()
    json_header = {"content-type": "application/json"}
    responses = [client.post(URL, json=rejection_payload(case[1])) for case in REJECTIONS]
    responses += [
        client.post(URL, content=b"{oops", headers=json_header),
        client.post(URL, headers=json_header),
        client.post(URL, json=[1]),
        client.post(URL, content=b"x", headers={"content-type": "text/plain"}),
    ]
    assert {response.status_code for response in responses} == {400}


@pytest.mark.parametrize("temperature", [0, 2])
def test_temperature_boundaries_are_accepted(temperature: float) -> None:
    assert make_client().post(URL, json=valid_payload(temperature=temperature)).status_code == 200


def test_n_equal_to_one_is_accepted() -> None:
    assert make_client().post(URL, json=valid_payload(n=1)).status_code == 200


@pytest.mark.parametrize("field", ["max_tokens", "max_completion_tokens"])
def test_each_token_cap_field_is_accepted(field: str) -> None:
    assert make_client().post(URL, json=valid_payload(**{field: 10})).status_code == 200


def test_optional_message_name_and_user_are_accepted() -> None:
    messages = [{"role": "user", "content": "hi", "name": "ada"}]
    assert (
        make_client().post(URL, json=valid_payload(messages=messages, user="u1")).status_code == 200
    )


def test_lone_surrogate_content_returns_400_through_the_real_route() -> None:
    response = make_client().post(
        URL,
        content=b'{"model":"m","messages":[{"role":"user","content":"\\ud800"}]}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["param"] == "messages[0].content"


def test_deeply_nested_body_returns_the_adr_0008_body_through_the_real_route() -> None:
    response = make_client().post(
        URL, content=b"[" * 100_000 + b"]" * 100_000, headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_json"


def test_unknown_request_fields_are_ignored() -> None:
    assert make_client().post(URL, json=valid_payload(top_p=0.2, stop=["x"])).status_code == 200


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return await MockProvider(FakeClock(7.0), FixedIdSource("chatcmpl-recorded")).complete(
            request
        )


def test_injected_provider_is_the_one_that_answers() -> None:
    provider = RecordingProvider()
    client = TestClient(
        create_app(make_settings(), FakeClock(), provider=provider), headers=AUTH_HEADERS
    )
    body = client.post(URL, json=valid_payload()).json()
    assert body["id"] == "chatcmpl-recorded"
    assert [request.model for request in provider.requests] == ["mock-1"]


def test_invalid_request_never_reaches_the_provider() -> None:
    provider = RecordingProvider()
    client = TestClient(
        create_app(make_settings(), FakeClock(), provider=provider), headers=AUTH_HEADERS
    )
    client.post(URL, json=valid_payload(stream=True))
    assert provider.requests == []


def test_default_provider_is_a_mock_provider_using_the_injected_clock() -> None:
    client = TestClient(create_app(make_settings(), FakeClock(42.0)), headers=AUTH_HEADERS)
    body = client.post(URL, json=valid_payload()).json()
    assert body["created"] == 42
    assert body["id"].startswith("chatcmpl-")


def test_health_is_unchanged_by_the_new_route() -> None:
    response = make_client().get("/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})
