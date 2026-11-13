"""The OpenAI-style error body and the handler that turns validation failures into 400 (ADR-0008).

FastAPI answers invalid requests with 422 and documents that 422 in the OpenAPI document. This
module replaces the runtime response with a 400 in the ADR-0008 shape, and provides the function
that removes the 422 from the generated document.
"""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.api.models import UNSUPPORTED_PARAMETER

INVALID_REQUEST_ERROR = "invalid_request_error"

# The detail FastAPI gives its 400 when a body cannot be read as JSON for a reason other than a
# syntax error, such as nesting deeper than the parser allows (fastapi/routing.py). A test pins it.
BODY_PARSE_FAILURE_DETAIL = "There was an error parsing the body"

# Pydantic error types that mean "the value has the wrong type". An explicit set, not a prefix rule,
# so a new pydantic error type falls through to invalid_value instead of being guessed.
INVALID_TYPE_ERRORS = frozenset(
    {
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
    }
)

_VALIDATION_SCHEMA_NAMES = ("HTTPValidationError", "ValidationError")


class ErrorBody(BaseModel):
    message: str
    type: str
    param: str | None
    code: str | None


class ErrorResponse(BaseModel):
    error: ErrorBody


def format_param(loc: Sequence[int | str]) -> str | None:
    """Name the field a pydantic location points at, as OpenAI does: messages[0].role."""
    parts = loc[1:] if loc and loc[0] == "body" else loc
    param = ""
    for part in parts:
        if isinstance(part, int):
            param += f"[{part}]"
        elif param:
            param += f".{part}"
        else:
            param = part
    return param or None


def code_for(error_type: str) -> str:
    if error_type == UNSUPPORTED_PARAMETER:
        return UNSUPPORTED_PARAMETER
    if error_type == "missing":
        return "missing_required_parameter"
    if error_type == "json_invalid":
        return "invalid_json"
    if error_type in INVALID_TYPE_ERRORS:
        return "invalid_type"
    return "invalid_value"


def error_body_for(error: dict[str, Any]) -> ErrorBody:
    """Map one pydantic error. Only type, loc and msg are read: input could hold prompt text."""
    error_type = str(error["type"])
    param = None if error_type == "json_invalid" else format_param(error["loc"])
    message = str(error["msg"])
    if error_type != UNSUPPORTED_PARAMETER and param is not None:
        message = f"Invalid '{param}': {message}"
    return ErrorBody(
        message=message, type=INVALID_REQUEST_ERROR, param=param, code=code_for(error_type)
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = exc.errors()
    if errors:
        body = error_body_for(dict(errors[0]))
    else:
        body = ErrorBody(
            message="Invalid request", type=INVALID_REQUEST_ERROR, param=None, code="invalid_value"
        )
    return JSONResponse(status_code=400, content=ErrorResponse(error=body).model_dump())


async def handle_http_exception(request: Request, exc: Exception) -> Response:
    """Give FastAPI's body-parsing 400 the ADR-0008 shape; other HTTPExceptions are unchanged."""
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if exc.status_code == 400 and exc.detail == BODY_PARSE_FAILURE_DETAIL:
        body = ErrorBody(
            message="The request body could not be parsed",
            type=INVALID_REQUEST_ERROR,
            param=None,
            code="invalid_json",
        )
        return JSONResponse(status_code=400, content=ErrorResponse(error=body).model_dump())
    return await http_exception_handler(request, exc)


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(RequestValidationError, handle_validation_error)
    application.add_exception_handler(StarletteHTTPException, handle_http_exception)


def _refs_validation_error(response: Any) -> bool:
    text = str(response)
    return any(f"#/components/schemas/{name}" in text for name in _VALIDATION_SCHEMA_NAMES)


def strip_validation_error_schemas(document: dict[str, Any]) -> dict[str, Any]:
    """Remove FastAPI's automatic 422 responses and their schemas. Idempotent; edits in place."""
    for path_item in document.get("paths", {}).values():
        for operation in path_item.values():
            responses = operation.get("responses", {}) if isinstance(operation, dict) else {}
            if "422" in responses and _refs_validation_error(responses["422"]):
                del responses["422"]
    schemas = document.get("components", {}).get("schemas", {})
    for name in _VALIDATION_SCHEMA_NAMES:
        schemas.pop(name, None)
    return document
