from typing import Any

import pytest
from pydantic import ValidationError

from app.api.models import ChatRequest


def request_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": "mock-1", "messages": [{"role": "user", "content": "hi"}]}
    payload.update(overrides)
    return payload


def error_types(payload: dict[str, Any]) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        ChatRequest.model_validate(payload)
    return [str(error["type"]) for error in caught.value.errors()]


@pytest.mark.parametrize("temperature", [0, 0.0, 1, 2, 2.0])
def test_temperature_accepts_values_from_0_to_2_inclusive(temperature: float) -> None:
    assert ChatRequest.model_validate(request_payload(temperature=temperature)).temperature == (
        temperature
    )


@pytest.mark.parametrize("temperature", [2.0001, 3, -0.1, -1])
def test_temperature_rejects_values_outside_0_to_2(temperature: float) -> None:
    assert error_types(request_payload(temperature=temperature)) in (
        ["less_than_equal"],
        ["greater_than_equal"],
    )


@pytest.mark.parametrize("n", [1, None])
def test_n_accepts_one_and_null(n: int | None) -> None:
    assert ChatRequest.model_validate(request_payload(n=n)).n == n


def test_n_above_one_is_unsupported_parameter() -> None:
    assert error_types(request_payload(n=2)) == ["unsupported_parameter"]


@pytest.mark.parametrize("n", [0, -1])
def test_n_below_one_is_invalid_value_not_unsupported(n: int) -> None:
    assert error_types(request_payload(n=n)) == ["greater_than_equal"]


@pytest.mark.parametrize("stream", [False, None])
def test_stream_false_and_null_are_accepted(stream: bool | None) -> None:
    assert ChatRequest.model_validate(request_payload(stream=stream)).stream is stream


def test_stream_true_is_unsupported_parameter() -> None:
    assert error_types(request_payload(stream=True)) == ["unsupported_parameter"]


def test_array_content_is_unsupported_parameter() -> None:
    messages = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    assert error_types(request_payload(messages=messages)) == ["unsupported_parameter"]


def test_empty_array_content_is_unsupported_parameter() -> None:
    messages = [{"role": "user", "content": []}]
    assert error_types(request_payload(messages=messages)) == ["unsupported_parameter"]


def test_empty_string_content_is_accepted() -> None:
    messages = [{"role": "user", "content": ""}]
    assert ChatRequest.model_validate(request_payload(messages=messages)).messages[0].content == ""


@pytest.mark.parametrize("content", [5, None, {"text": "hi"}])
def test_non_string_non_array_content_is_a_string_type_error(content: Any) -> None:
    messages = [{"role": "user", "content": content}]
    assert error_types(request_payload(messages=messages)) == ["string_type"]


@pytest.mark.parametrize("role", ["system", "user", "assistant"])
def test_role_accepts_system_user_and_assistant(role: str) -> None:
    messages = [{"role": role, "content": "x"}]
    assert ChatRequest.model_validate(request_payload(messages=messages)).messages[0].role == role


@pytest.mark.parametrize("role", ["User", "SYSTEM", "developer", "tool", "function", "", " user"])
def test_role_rejects_lookalikes_and_other_roles(role: str) -> None:
    messages = [{"role": role, "content": "x"}]
    assert error_types(request_payload(messages=messages)) == ["literal_error"]


def test_name_is_optional() -> None:
    absent = ChatRequest.model_validate(request_payload())
    explicit_null = ChatRequest.model_validate(
        request_payload(messages=[{"role": "user", "content": "x", "name": None}])
    )
    present = ChatRequest.model_validate(
        request_payload(messages=[{"role": "user", "content": "x", "name": "ada"}])
    )
    assert (absent.messages[0].name, explicit_null.messages[0].name) == (None, None)
    assert present.messages[0].name == "ada"


def test_messages_must_not_be_empty() -> None:
    assert error_types(request_payload(messages=[])) == ["too_short"]


def test_messages_and_model_are_required() -> None:
    payload = request_payload()
    del payload["model"]
    del payload["messages"]
    assert error_types(payload) == ["missing", "missing"]


def test_model_must_not_be_empty() -> None:
    assert error_types(request_payload(model="")) == ["string_too_short"]


def test_token_caps_are_accepted_together_and_must_be_positive() -> None:
    parsed = ChatRequest.model_validate(request_payload(max_tokens=5, max_completion_tokens=7))
    assert (parsed.max_tokens, parsed.max_completion_tokens) == (5, 7)
    assert error_types(request_payload(max_tokens=0)) == ["greater_than_equal"]
    assert error_types(request_payload(max_completion_tokens=0)) == ["greater_than_equal"]


def test_optional_fields_accept_null() -> None:
    parsed = ChatRequest.model_validate(
        request_payload(
            max_tokens=None,
            max_completion_tokens=None,
            temperature=None,
            n=None,
            stream=None,
            user=None,
        )
    )
    assert parsed.temperature is None
    assert parsed.user is None


def test_unknown_fields_are_ignored() -> None:
    parsed = ChatRequest.model_validate(request_payload(top_p=0.5, stop=["x"]))
    assert not hasattr(parsed, "top_p")
