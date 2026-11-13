import json
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeClock, make_settings

ROUTE = "/v1/chat/completions"


def document() -> dict[str, Any]:
    return create_app(make_settings(), FakeClock()).openapi()


def test_route_documents_exactly_the_200_and_400_responses() -> None:
    responses = document()["paths"][ROUTE]["post"]["responses"]
    assert set(responses) == {"200", "400"}
    ok = responses["200"]["content"]["application/json"]["schema"]
    bad = responses["400"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/ChatResponse"}
    assert bad == {"$ref": "#/components/schemas/ErrorResponse"}


def test_route_accepts_only_post() -> None:
    assert set(document()["paths"][ROUTE]) == {"post"}


def test_document_has_no_422_and_no_validation_error_schemas() -> None:
    text = json.dumps(document())
    assert '"422"' not in text
    assert "ValidationError" not in text


def test_openapi_json_endpoint_serves_the_same_stripped_document() -> None:
    served = TestClient(create_app(make_settings(), FakeClock())).get("/openapi.json").json()
    assert served == document()


def test_error_body_schema_requires_all_four_fields_and_nulls_param_and_code() -> None:
    schemas = document()["components"]["schemas"]
    body = schemas["ErrorBody"]
    assert set(body["required"]) == {"message", "type", "param", "code"}
    for nullable in ("param", "code"):
        assert {"type": "null"} in body["properties"][nullable]["anyOf"]
    assert schemas["ErrorResponse"]["required"] == ["error"]


def test_request_schema_requires_model_and_messages_and_bounds_temperature() -> None:
    request = document()["components"]["schemas"]["ChatRequest"]
    assert set(request["required"]) == {"model", "messages"}
    temperature = next(
        option for option in request["properties"]["temperature"]["anyOf"] if "minimum" in option
    )
    assert (temperature["minimum"], temperature["maximum"]) == (0, 2)
    assert request["properties"]["messages"]["minItems"] == 1


def test_schemas_added_are_only_the_chat_models_and_the_error_model() -> None:
    names = set(document()["components"]["schemas"])
    assert names == {
        "ChatMessage",
        "ChatRequest",
        "ChatResponse",
        "Choice",
        "ErrorBody",
        "ErrorResponse",
        "HealthResponse",
        "ResponseMessage",
        "Usage",
    }
