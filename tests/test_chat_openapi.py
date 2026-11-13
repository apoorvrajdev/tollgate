import json
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeClock, make_settings

ROUTE = "/v1/chat/completions"


def document() -> dict[str, Any]:
    return create_app(make_settings(), FakeClock()).openapi()


LIMIT_HEADER_NAMES = {
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
}


ROUTING_HEADER_NAMES = {"x-tollgate-provider", "x-tollgate-fallbacks"}


def test_route_documents_exactly_the_200_400_401_404_429_and_502_responses() -> None:
    responses = document()["paths"][ROUTE]["post"]["responses"]
    assert set(responses) == {"200", "400", "401", "404", "429", "502"}
    ok = responses["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/ChatResponse"}
    assert responses["200"]["description"] == "Successful Response"
    for status in ("400", "401", "404", "429", "502"):
        schema = responses[status]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, status


def test_limit_headers_are_documented_on_200_429_and_502_and_retry_after_only_on_429() -> None:
    responses = document()["paths"][ROUTE]["post"]["responses"]
    assert set(responses["200"]["headers"]) == LIMIT_HEADER_NAMES | ROUTING_HEADER_NAMES
    assert set(responses["429"]["headers"]) == LIMIT_HEADER_NAMES | {"Retry-After"}
    assert set(responses["502"]["headers"]) == LIMIT_HEADER_NAMES
    assert "headers" not in responses["400"]
    assert "headers" not in responses["404"]
    assert set(responses["401"]["headers"]) == {"WWW-Authenticate"}
    types = {name: spec["schema"]["type"] for name, spec in responses["429"]["headers"].items()}
    assert types == {
        "x-ratelimit-limit-tokens": "integer",
        "x-ratelimit-remaining-tokens": "integer",
        "x-ratelimit-reset-tokens": "string",
        "Retry-After": "integer",
    }


def test_routing_headers_are_documented_on_200_with_their_types() -> None:
    headers = document()["paths"][ROUTE]["post"]["responses"]["200"]["headers"]
    types = {name: headers[name]["schema"]["type"] for name in ROUTING_HEADER_NAMES}
    assert types == {"x-tollgate-provider": "string", "x-tollgate-fallbacks": "integer"}


def test_401_documents_the_www_authenticate_challenge_header() -> None:
    headers = document()["paths"][ROUTE]["post"]["responses"]["401"]["headers"]
    assert set(headers) == {"WWW-Authenticate"}
    assert headers["WWW-Authenticate"]["schema"] == {"type": "string"}


def test_document_records_the_bearer_scheme_and_the_route_requires_it() -> None:
    doc = document()
    schemes = doc["components"]["securitySchemes"]
    assert set(schemes) == {"ApiKeyAuth"}
    assert (schemes["ApiKeyAuth"]["type"], schemes["ApiKeyAuth"]["scheme"]) == ("http", "bearer")
    assert doc["paths"][ROUTE]["post"]["security"] == [{"ApiKeyAuth": []}]


def test_health_and_the_document_as_a_whole_declare_no_security_requirement() -> None:
    doc = document()
    assert "security" not in doc["paths"]["/health"]["get"]
    assert "security" not in doc


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
