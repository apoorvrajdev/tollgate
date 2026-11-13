import asyncio
import copy
import json
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import (
    BODY_PARSE_FAILURE_DETAIL,
    INVALID_TYPE_ERRORS,
    ErrorBody,
    ErrorResponse,
    code_for,
    format_param,
    handle_http_exception,
    handle_validation_error,
    register_error_handlers,
    strip_validation_error_schemas,
)
from app.api.models import ChatRequest

SENTINEL = "SENTINEL-prompt-text-7f3a"


def make_client() -> TestClient:
    """A scratch app: one route that validates a ChatRequest, with the error handler registered."""
    scratch = FastAPI()
    register_error_handlers(scratch)

    @scratch.post("/probe")
    def probe(body: ChatRequest) -> dict[str, str]:
        return {"model": body.model}

    return TestClient(scratch)


def valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": "mock-1", "messages": [{"role": "user", "content": "hi"}]}
    payload.update(overrides)
    return payload


def rejected(payload: dict[str, Any]) -> dict[str, Any]:
    response = make_client().post("/probe", json=payload)
    assert response.status_code == 400
    error: dict[str, Any] = response.json()["error"]
    return error


def test_valid_request_passes_through_the_scratch_app() -> None:
    assert make_client().post("/probe", json=valid_payload()).status_code == 200


def test_missing_model_maps_to_missing_required_parameter_with_param_model() -> None:
    payload = valid_payload()
    del payload["model"]
    error = rejected(payload)
    assert (error["param"], error["code"]) == ("model", "missing_required_parameter")
    assert error["type"] == "invalid_request_error"


def test_error_body_has_exactly_message_type_param_code() -> None:
    error = rejected(valid_payload(temperature=3))
    assert set(error) == {"message", "type", "param", "code"}
    assert isinstance(error["message"], str)


def test_error_response_wraps_the_body_under_error() -> None:
    body = ErrorBody(message="m", type="t", param=None, code=None)
    assert ErrorResponse(error=body).model_dump() == {
        "error": {"message": "m", "type": "t", "param": None, "code": None}
    }


def test_nested_param_uses_bracket_and_dot_format() -> None:
    messages = [
        {"role": "user", "content": "ok"},
        {"role": "developer", "content": "x"},
    ]
    assert rejected(valid_payload(messages=messages))["param"] == "messages[1].role"
    messages = [{"role": "user", "content": "ok"}, {"role": "user"}]
    assert rejected(valid_payload(messages=messages))["param"] == "messages[1].content"


def test_format_param_handles_each_location_shape() -> None:
    assert format_param(("body", "model")) == "model"
    assert format_param(("body", "messages", 0, "role")) == "messages[0].role"
    assert format_param(("body", "messages", 2)) == "messages[2]"
    assert format_param(("body",)) is None
    assert format_param(()) is None


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        ("missing", "missing_required_parameter"),
        ("unsupported_parameter", "unsupported_parameter"),
        ("json_invalid", "invalid_json"),
        ("literal_error", "invalid_value"),
        ("greater_than_equal", "invalid_value"),
        ("less_than_equal", "invalid_value"),
        ("too_short", "invalid_value"),
        ("string_too_short", "invalid_value"),
        ("int_from_float", "invalid_value"),
        ("some_future_error_type", "invalid_value"),
    ],
)
def test_code_for_maps_each_error_class(error_type: str, code: str) -> None:
    assert code_for(error_type) == code


@pytest.mark.parametrize(
    "error_type",
    [
        "string_type",
        "int_type",
        "float_type",
        "bool_type",
        "list_type",
        "dict_type",
        "model_attributes_type",
        "int_parsing",
        "float_parsing",
        "bool_parsing",
    ],
)
def test_every_wrong_type_error_maps_to_invalid_type(error_type: str) -> None:
    # A literal list, not the set itself, so removing a member from the set is noticed.
    assert code_for(error_type) == "invalid_type"
    assert error_type in INVALID_TYPE_ERRORS


@pytest.mark.parametrize(
    ("overrides", "param"),
    [
        ({"n": "abc"}, "n"),
        ({"max_tokens": "abc"}, "max_tokens"),
        ({"max_completion_tokens": "abc"}, "max_completion_tokens"),
        ({"temperature": "hot"}, "temperature"),
        ({"stream": "maybe"}, "stream"),
        ({"n": [1]}, "n"),
        ({"max_tokens": [1]}, "max_tokens"),
        ({"temperature": [1]}, "temperature"),
        ({"stream": [1]}, "stream"),
        ({"user": 5}, "user"),
        ({"model": 5}, "model"),
        ({"messages": "hello"}, "messages"),
        ({"messages": ["x"]}, "messages[0]"),
    ],
)
def test_wrong_type_for_each_field_kind_is_invalid_type(
    overrides: dict[str, Any], param: str
) -> None:
    error = rejected(valid_payload(**overrides))
    assert (error["param"], error["code"]) == (param, "invalid_type")


def test_fractional_number_for_an_integer_field_is_invalid_value_not_invalid_type() -> None:
    error = rejected(valid_payload(n=1.5))
    assert (error["param"], error["code"]) == ("n", "invalid_value")


@pytest.mark.parametrize(
    ("overrides", "param", "code"),
    [
        ({"temperature": "hot"}, "temperature", "invalid_type"),
        ({"temperature": 3}, "temperature", "invalid_value"),
        ({"n": 2}, "n", "unsupported_parameter"),
        ({"n": 0}, "n", "invalid_value"),
        ({"stream": True}, "stream", "unsupported_parameter"),
        ({"messages": []}, "messages", "invalid_value"),
        ({"messages": "hello"}, "messages", "invalid_type"),
        ({"max_tokens": 0}, "max_tokens", "invalid_value"),
    ],
)
def test_each_rejection_maps_to_its_param_and_code(
    overrides: dict[str, Any], param: str, code: str
) -> None:
    error = rejected(valid_payload(**overrides))
    assert (error["param"], error["code"]) == (param, code)


def test_array_and_non_string_content_map_to_distinct_codes() -> None:
    array = rejected(valid_payload(messages=[{"role": "user", "content": ["x"]}]))
    number = rejected(valid_payload(messages=[{"role": "user", "content": 5}]))
    assert (array["param"], array["code"]) == ("messages[0].content", "unsupported_parameter")
    assert (number["param"], number["code"]) == ("messages[0].content", "invalid_type")


def test_unknown_role_maps_to_invalid_value() -> None:
    error = rejected(valid_payload(messages=[{"role": "tool", "content": "x"}]))
    assert (error["param"], error["code"]) == ("messages[0].role", "invalid_value")


def test_malformed_json_returns_400_with_null_param() -> None:
    response = make_client().post(
        "/probe", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert (error["param"], error["code"]) == (None, "invalid_json")


def test_empty_body_returns_400_missing_required_parameter() -> None:
    response = make_client().post("/probe", headers={"content-type": "application/json"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert (error["param"], error["code"]) == (None, "missing_required_parameter")


def test_json_list_body_returns_400_invalid_type() -> None:
    response = make_client().post("/probe", json=[1, 2])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_type"


def test_lone_surrogate_in_content_is_rejected_not_a_server_error() -> None:
    response = make_client().post(
        "/probe",
        content=b'{"model":"m","messages":[{"role":"user","content":"\\ud800"}]}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert (error["param"], error["code"]) == ("messages[0].content", "invalid_value")


def test_valid_non_ascii_content_is_accepted() -> None:
    messages = [{"role": "user", "content": "café 世界 \U0001f600"}]
    assert make_client().post("/probe", json=valid_payload(messages=messages)).status_code == 200


def test_deeply_nested_json_gets_the_adr_0008_body_not_fastapis_detail() -> None:
    depth = 100_000
    response = make_client().post(
        "/probe",
        content=b"[" * depth + b"]" * depth,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == {
        "message": "The request body could not be parsed",
        "type": "invalid_request_error",
        "param": None,
        "code": "invalid_json",
    }


def scratch_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def test_parse_failure_detail_on_a_non_400_status_is_not_reshaped() -> None:
    exc = StarletteHTTPException(status_code=500, detail=BODY_PARSE_FAILURE_DETAIL)
    response = asyncio.run(handle_http_exception(scratch_request(), exc))
    assert response.status_code == 500
    assert json.loads(bytes(response.body)) == {"detail": BODY_PARSE_FAILURE_DETAIL}


def test_other_400_details_are_not_reshaped() -> None:
    exc = StarletteHTTPException(status_code=400, detail="something else")
    response = asyncio.run(handle_http_exception(scratch_request(), exc))
    assert json.loads(bytes(response.body)) == {"detail": "something else"}


def test_validation_error_without_details_still_gets_a_400_error_body() -> None:
    response = asyncio.run(handle_validation_error(scratch_request(), RequestValidationError([])))
    assert response.status_code == 400
    assert json.loads(bytes(response.body))["error"] == {
        "message": "Invalid request",
        "type": "invalid_request_error",
        "param": None,
        "code": "invalid_value",
    }


def test_handlers_re_raise_exceptions_of_other_types() -> None:
    with pytest.raises(ValueError, match="boom"):
        asyncio.run(handle_http_exception(scratch_request(), ValueError("boom")))
    with pytest.raises(ValueError, match="boom"):
        asyncio.run(handle_validation_error(scratch_request(), ValueError("boom")))


def test_other_http_exceptions_keep_fastapis_default_body() -> None:
    client = make_client()
    missing = client.get("/no-such-route")
    wrong_method = client.get("/probe")
    assert (missing.status_code, missing.json()) == (404, {"detail": "Not Found"})
    assert (wrong_method.status_code, wrong_method.json()) == (
        405,
        {"detail": "Method Not Allowed"},
    )


def test_wrong_boolean_value_maps_to_invalid_type() -> None:
    error = rejected(valid_payload(stream="maybe"))
    assert (error["param"], error["code"]) == ("stream", "invalid_type")


def test_text_plain_body_returns_400_not_422() -> None:
    response = make_client().post(
        "/probe", content=b"hello", headers={"content-type": "text/plain"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


@pytest.mark.parametrize(
    "overrides",
    [
        {"temperature": SENTINEL},
        {"n": SENTINEL},
        {"stream": SENTINEL},
        {"max_tokens": SENTINEL},
        {"model": {"k": SENTINEL}},
        {"messages": [{"role": SENTINEL, "content": "x"}]},
        {"messages": [{"role": "user", "content": {"k": SENTINEL}}]},
        {"messages": [{"role": "user", "content": [SENTINEL]}]},
        {"messages": SENTINEL},
    ],
)
def test_rejected_value_is_never_echoed_in_the_response(overrides: dict[str, Any]) -> None:
    response = make_client().post("/probe", json=valid_payload(**overrides))
    assert response.status_code == 400
    assert SENTINEL not in response.text


def test_first_error_wins_in_field_order() -> None:
    error = rejected(valid_payload(model="", messages=[], temperature=3))
    assert error["param"] == "model"


def test_unsupported_parameter_message_is_the_fixed_text_without_a_prefix() -> None:
    error = rejected(valid_payload(stream=True))
    assert error["message"] == "Streaming is not supported"


def test_other_messages_name_the_param() -> None:
    error = rejected(valid_payload(temperature=3))
    assert error["message"].startswith("Invalid 'temperature': ")


def openapi_with_validation_errors() -> dict[str, Any]:
    ref = {"$ref": "#/components/schemas/HTTPValidationError"}
    return {
        "paths": {
            "/a": {
                "post": {
                    "responses": {
                        "200": {"description": "ok"},
                        "400": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                            "description": "bad",
                        },
                        "422": {
                            "content": {"application/json": {"schema": ref}},
                            "description": "Validation Error",
                        },
                    }
                },
                "parameters": [],
            }
        },
        "components": {
            "schemas": {
                "ErrorResponse": {"type": "object"},
                "HTTPValidationError": {"type": "object"},
                "ValidationError": {"type": "object"},
                "Other": {"type": "object"},
            }
        },
    }


def test_strip_removes_422_and_validation_schemas_only() -> None:
    stripped = strip_validation_error_schemas(openapi_with_validation_errors())
    assert set(stripped["paths"]["/a"]["post"]["responses"]) == {"200", "400"}
    assert set(stripped["components"]["schemas"]) == {"ErrorResponse", "Other"}


def test_strip_is_idempotent() -> None:
    once = strip_validation_error_schemas(openapi_with_validation_errors())
    twice = strip_validation_error_schemas(copy.deepcopy(once))
    assert once == twice


def test_strip_keeps_a_422_that_does_not_reference_the_validation_schemas() -> None:
    document = openapi_with_validation_errors()
    document["paths"]["/a"]["post"]["responses"]["422"] = {"description": "custom"}
    stripped = strip_validation_error_schemas(document)
    assert "422" in stripped["paths"]["/a"]["post"]["responses"]


def test_strip_tolerates_a_document_without_components() -> None:
    assert strip_validation_error_schemas({"paths": {}}) == {"paths": {}}
