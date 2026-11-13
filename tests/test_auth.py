import asyncio
import dataclasses
import hashlib
from typing import Any

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api import auth
from app.api.auth import (
    ApiKeyAuthenticator,
    CallerIdentity,
    InvalidApiKeyError,
    handle_invalid_api_key,
    register_auth_error_handler,
    require_api_key,
)
from tests.auth_cases import ACCEPTED_HEADER_VALUES, EXPECTED_401_BODY, REJECTED_HEADER_VALUES
from tests.fakes import TEST_API_KEY

SENTINEL = "SENTINEL-key-9c1d"
ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def make_authenticator(*keys: str) -> ApiKeyAuthenticator:
    return ApiKeyAuthenticator([SecretStr(key) for key in keys])


@pytest.mark.parametrize("values", REJECTED_HEADER_VALUES.values(), ids=REJECTED_HEADER_VALUES)
def test_malformed_or_wrong_authorization_values_are_rejected(values: list[str]) -> None:
    with pytest.raises(InvalidApiKeyError):
        make_authenticator(TEST_API_KEY).authenticate(values)


@pytest.mark.parametrize("value", ACCEPTED_HEADER_VALUES.values(), ids=ACCEPTED_HEADER_VALUES)
def test_scheme_is_case_insensitive_and_extra_spaces_are_accepted(value: str) -> None:
    identity = make_authenticator(TEST_API_KEY).authenticate([value])
    assert identity.caller_id == hashlib.sha256(TEST_API_KEY.encode()).hexdigest()


def test_each_configured_key_is_accepted_first_middle_and_last() -> None:
    authenticator = make_authenticator("key-one", "key-two", "key-three")
    for key in ("key-one", "key-two", "key-three"):
        assert authenticator.authenticate([f"Bearer {key}"]).caller_id


def test_a_key_that_is_not_configured_is_rejected_among_several() -> None:
    authenticator = make_authenticator("key-one", "key-two", "key-three")
    with pytest.raises(InvalidApiKeyError):
        authenticator.authenticate(["Bearer key-four"])


def test_caller_id_is_the_sha256_hex_of_the_key() -> None:
    # The literal is the standard SHA-256 test vector for "abc".
    assert make_authenticator("abc").authenticate(["Bearer abc"]).caller_id == ABC_SHA256


def test_distinct_keys_give_distinct_ids_and_one_key_gives_a_stable_id() -> None:
    authenticator = make_authenticator("key-one", "key-two")
    one = authenticator.authenticate(["Bearer key-one"]).caller_id
    two = authenticator.authenticate(["Bearer key-two"]).caller_id
    assert one != two
    assert authenticator.authenticate(["Bearer key-one"]).caller_id == one
    assert len(one) == 64


def test_identity_holds_only_the_digest() -> None:
    identity = make_authenticator(SENTINEL).authenticate([f"Bearer {SENTINEL}"])
    assert [field.name for field in dataclasses.fields(identity)] == ["caller_id"]
    assert identity.caller_id != SENTINEL
    assert SENTINEL not in repr(identity)
    assert SENTINEL not in str(identity)
    assert SENTINEL not in str(dataclasses.asdict(identity))


def test_identity_is_immutable() -> None:
    identity = CallerIdentity(caller_id="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.caller_id = "y"  # type: ignore[misc]


def test_authenticator_keeps_digests_and_no_key_text() -> None:
    authenticator = make_authenticator(SENTINEL)
    assert SENTINEL not in repr(vars(authenticator))
    assert SENTINEL not in repr(authenticator)
    assert vars(authenticator)["_digests"] == (hashlib.sha256(SENTINEL.encode()).digest(),)


def test_a_configured_key_is_matched_exactly_including_its_spaces() -> None:
    # Settings trims keys before they reach the authenticator; the authenticator itself must not.
    with pytest.raises(InvalidApiKeyError):
        make_authenticator(" key").authenticate(["Bearer key"])


@pytest.mark.parametrize(
    "value",
    [" Bearer test-key", "\tBearer test-key", "\xa0Bearer test-key", " test-key"],
    ids=["space before scheme", "tab before scheme", "NBSP before scheme", "empty scheme"],
)
def test_leading_whitespace_before_the_scheme_is_rejected(value: str) -> None:
    with pytest.raises(InvalidApiKeyError):
        make_authenticator("test-key").authenticate([value])


def test_a_configured_key_with_an_internal_space_is_matched_with_that_space() -> None:
    # Settings keeps internal spaces: it splits the variable on commas only.
    assert make_authenticator("a key").authenticate(["Bearer a key"]).caller_id
    with pytest.raises(InvalidApiKeyError):
        make_authenticator("a key").authenticate(["Bearer akey"])


@pytest.mark.parametrize("value", ["Bearer test-key", "Bearer "])
def test_an_authenticator_with_no_keys_rejects_everything(value: str) -> None:
    with pytest.raises(InvalidApiKeyError):
        make_authenticator().authenticate([value])


def test_an_empty_configured_key_never_authenticates() -> None:
    with pytest.raises(InvalidApiKeyError):
        make_authenticator("").authenticate(["Bearer "])


def test_non_ascii_configured_key_is_accepted_and_a_lookalike_is_not() -> None:
    authenticator = make_authenticator("clé-ü")
    assert authenticator.authenticate(["Bearer clé-ü"]).caller_id
    with pytest.raises(InvalidApiKeyError):
        authenticator.authenticate(["Bearer cle-u"])


def test_a_lone_surrogate_in_the_submitted_key_is_rejected_without_a_type_error() -> None:
    authenticator = make_authenticator("a?")
    with pytest.raises(InvalidApiKeyError):
        authenticator.authenticate(["Bearer a\ud800"])


def test_error_carries_no_input() -> None:
    with pytest.raises(InvalidApiKeyError) as caught:
        make_authenticator(TEST_API_KEY).authenticate([f"Bearer {SENTINEL}"])
    digest_hex = hashlib.sha256(SENTINEL.encode()).hexdigest()
    for text in (str(caught.value), repr(caught.value), str(caught.value.args)):
        assert SENTINEL not in text
        assert digest_hex not in text
    assert caught.value.args == ("Invalid API key",)


class CountingHmac:
    """Stands in for the hmac module and records what compare_digest is given."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    def compare_digest(self, first: bytes, second: bytes) -> bool:
        self.calls.append((first, second))
        return first == second


@pytest.mark.parametrize(
    ("submitted", "matches"),
    [("key-one", True), ("key-two", True), ("key-three", True), ("nope", False)],
)
def test_every_configured_key_is_compared_with_no_early_exit(
    monkeypatch: pytest.MonkeyPatch, submitted: str, matches: bool
) -> None:
    authenticator = make_authenticator("key-one", "key-two", "key-three")
    spy = CountingHmac()
    monkeypatch.setattr(auth, "hmac", spy)
    if matches:
        authenticator.authenticate([f"Bearer {submitted}"])
    else:
        with pytest.raises(InvalidApiKeyError):
            authenticator.authenticate([f"Bearer {submitted}"])
    assert len(spy.calls) == 3
    assert all(
        isinstance(first, bytes) and isinstance(second, bytes) and len(first) == len(second) == 32
        for first, second in spy.calls
    )


def test_comparison_is_not_attempted_for_malformed_headers() -> None:
    # Nothing is hashed or compared when there is no usable token, so these cannot reveal timing.
    spy = CountingHmac()
    authenticator = make_authenticator("key-one")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(auth, "hmac", spy)
        for values in ([], ["Bearer"], ["Basic abc"], ["Bearer a", "Bearer b"]):
            with pytest.raises(InvalidApiKeyError):
                authenticator.authenticate(values)
    assert spy.calls == []


def make_scratch_client() -> TestClient:
    scratch = FastAPI()
    scratch.state.authenticator = make_authenticator(TEST_API_KEY)
    register_auth_error_handler(scratch)

    @scratch.get("/whoami")
    def whoami(caller: auth.CallerIdentity = Depends(require_api_key)) -> dict[str, str]:  # noqa: B008
        return {"caller_id": caller.caller_id}

    return TestClient(scratch)


def test_dependency_returns_the_identity_of_the_submitted_key() -> None:
    response = make_scratch_client().get("/whoami", headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 200
    assert response.json() == {"caller_id": hashlib.sha256(b"test-key").hexdigest()}


def test_401_has_the_adr_0008_body_and_a_bearer_challenge() -> None:
    response = make_scratch_client().get("/whoami")
    assert response.status_code == 401
    assert response.json() == EXPECTED_401_BODY
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["content-type"] == "application/json"


def test_a_missing_key_and_a_wrong_key_get_the_same_401_body_without_echoing_the_key() -> None:
    client = make_scratch_client()
    wrong = client.get("/whoami", headers={"Authorization": f"Bearer {SENTINEL}"}).text
    missing = client.get("/whoami").text
    assert wrong == missing
    assert SENTINEL not in wrong


def test_handler_re_raises_exceptions_of_other_types() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    with pytest.raises(ValueError, match="boom"):
        asyncio.run(handle_invalid_api_key(request, ValueError("boom")))
