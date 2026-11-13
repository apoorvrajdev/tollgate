"""API key authentication for /v1/chat/completions (ADR-0008).

Keys come from configuration. The authenticator keeps only SHA-256 digests of them, and the digest
of the submitted key is the caller id, so it never stores, compares as text, logs or returns key
text. The configured keys themselves stay in Settings as SecretStr, masked in repr and errors.
The digests are unsalted, which is sound only for high-entropy keys.

Every failure gets the same 401 body, so a caller cannot tell a missing key from a wrong one.
"""

import hashlib
import hmac
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from app.api.errors import INVALID_REQUEST_ERROR, ErrorBody, ErrorResponse

SECURITY_SCHEME_NAME = "ApiKeyAuth"
INVALID_API_KEY_CODE = "invalid_api_key"
INVALID_API_KEY_MESSAGE = "Missing or invalid API key. Send it as 'Authorization: Bearer <key>'."
WWW_AUTHENTICATE_CHALLENGE = "Bearer"

# The 401 as documented in the OpenAPI document (ADR-0008).
UNAUTHORIZED_RESPONSE: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid API key",
        "headers": {
            "WWW-Authenticate": {
                "description": "The authentication challenge: Bearer",
                "schema": {"type": "string"},
            }
        },
    }
}

# Exists so the OpenAPI document records the bearer scheme. It never rejects a request itself
# (auto_error=False), because the 401 body must be ours, not FastAPI's.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name=SECURITY_SCHEME_NAME,
    description="API key sent as 'Authorization: Bearer <key>'",
)


class InvalidApiKeyError(Exception):
    """The request carries no valid API key. Carries no data, so nothing can echo the key."""

    def __init__(self) -> None:
        super().__init__("Invalid API key")


@dataclass(frozen=True, slots=True)
class CallerIdentity:
    """Who is calling. caller_id is the SHA-256 hex digest of the key, never the key."""

    caller_id: str


def _digest(text: str) -> bytes:
    # surrogatepass never raises and is injective, so two different strings cannot share bytes.
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).digest()


class ApiKeyAuthenticator:
    def __init__(self, keys: Sequence[SecretStr]) -> None:
        self._digests = tuple(_digest(key.get_secret_value()) for key in keys)

    def authenticate(self, authorization_values: Sequence[str]) -> CallerIdentity:
        """Check the Authorization header values of a request. Raises InvalidApiKeyError."""
        # More than one Authorization header is ambiguous: a proxy and this app could pick
        # different ones, so it is rejected.
        if len(authorization_values) != 1:
            raise InvalidApiKeyError
        scheme, _, rest = authorization_values[0].partition(" ")
        if scheme.lower() != "bearer":
            raise InvalidApiKeyError
        # Only spaces are trimmed (RFC 9110 allows one or more between scheme and credentials). A
        # tab between the scheme and the key, or other whitespace such as a non-breaking space
        # around the key, is part of what was submitted and will not match. (h11, which uvicorn
        # uses here, removes a trailing tab from the header value before this code sees it.)
        token = rest.strip(" ")
        if not token:
            raise InvalidApiKeyError
        submitted = _digest(token)
        # Every configured digest is compared, with no early exit, so the time taken does not
        # show which key matched. Comparing fixed-length digests hides the submitted key's length.
        matched = False
        for digest in self._digests:
            matched |= hmac.compare_digest(digest, submitted)
        if not matched:
            raise InvalidApiKeyError
        return CallerIdentity(caller_id=submitted.hex())


def authorization_values(request: Request) -> list[str]:
    """The Authorization header values, decoded as UTF-8 from the raw bytes.

    Starlette's request.headers decodes as latin-1, which would turn a UTF-8 key such as "clé"
    into different text than the configured key. Bytes that are not valid UTF-8 become lone
    surrogates, which cannot equal a key that is valid text.
    """
    return [
        value.decode("utf-8", errors="surrogateescape")
        for name, value in request.headers.raw
        if name.lower() == b"authorization"
    ]


def authenticate_request(request: Request) -> CallerIdentity:
    authenticator: ApiKeyAuthenticator = request.app.state.authenticator
    return authenticator.authenticate(authorization_values(request))


def require_api_key(
    request: Request,
    _credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CallerIdentity:
    """Dependency that returns the caller. The unused parameter puts the scheme in OpenAPI."""
    return authenticate_request(request)


class AuthenticatedRoute(APIRoute):
    """A route that authenticates before FastAPI reads or validates the body.

    A plain dependency runs after the body is parsed, so a malformed body would get a 400 before
    the 401. Checking first means an unauthenticated caller learns nothing about the schema.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            authenticate_request(request)
            return await original(request)

        return handler


async def handle_invalid_api_key(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, InvalidApiKeyError):
        raise exc
    body = ErrorBody(
        message=INVALID_API_KEY_MESSAGE,
        type=INVALID_REQUEST_ERROR,
        param=None,
        code=INVALID_API_KEY_CODE,
    )
    return JSONResponse(
        status_code=401,
        content=ErrorResponse(error=body).model_dump(),
        headers={"WWW-Authenticate": WWW_AUTHENTICATE_CHALLENGE},
    )


def register_auth_error_handler(application: FastAPI) -> None:
    application.add_exception_handler(InvalidApiKeyError, handle_invalid_api_key)
