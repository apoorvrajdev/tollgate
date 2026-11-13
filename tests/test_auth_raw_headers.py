"""Authorization header bytes that reach the app unchanged.

Starlette's TestClient re-encodes header values through httpx, so invalid UTF-8 never arrives
through it. These tests call the ASGI app directly with hand-built `scope["headers"]`, the way a
server such as uvicorn delivers them.
"""

import asyncio
import json
import unicodedata

import pytest
from starlette.requests import Request
from starlette.types import Message, Scope

from app.api.auth import authorization_values
from app.main import create_app
from tests.auth_cases import EXPECTED_401_BODY
from tests.fakes import FakeClock, make_settings

URL_PATH = "/v1/chat/completions"
BODY = json.dumps({"model": "mock-1", "messages": [{"role": "user", "content": "hi"}]}).encode()


def call(keys: str, headers: list[tuple[bytes, bytes]]) -> tuple[int, dict[bytes, bytes], bytes]:
    """POST a valid body with exactly these extra raw headers; return status, headers, body."""
    application = create_app(make_settings(TOLLGATE_API_KEYS=keys), FakeClock())
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": URL_PATH,
        "raw_path": URL_PATH.encode(),
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 5000),
        "server": ("test", 80),
        "headers": [(b"content-type", b"application/json"), *headers],
    }
    sent: list[Message] = []
    pending: list[Message] = [{"type": "http.request", "body": BODY, "more_body": False}]

    async def receive() -> Message:
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(application(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), payload


def status_for(keys: str, value: bytes, name: bytes = b"authorization") -> int:
    return call(keys, [(name, value)])[0]


@pytest.mark.parametrize(
    "value",
    [
        b"\xff",
        b"Bearer \xff\xfe\xfd",
        b"\xffearer test-key",
        b"Bearer t\xffest-key",
        b"Bearer \xed\xa0\x80",
        b"Bearer \xc0\xaf",
        b"Bearer \xe0\x80\x80",
        b"Bearer \xf8\x88\x80\x80\x80",
    ],
    ids=[
        "lone byte",
        "bytes in the key",
        "byte in the scheme",
        "byte inside the key",
        "encoded surrogate",
        "overlong slash",
        "overlong three-byte",
        "five-byte lead",
    ],
)
def test_invalid_utf8_header_bytes_get_the_standard_401_not_a_server_error(value: bytes) -> None:
    status, headers, payload = call("test-key", [(b"authorization", value)])
    assert status == 401
    assert json.loads(payload) == EXPECTED_401_BODY
    assert headers[b"www-authenticate"] == b"Bearer"


@pytest.mark.parametrize(
    "value",
    [b"Bearer test-key\xff", b"Bearer test-key\xc0\xaf", b"Bearer test-key\xe2\x82"],
    ids=["trailing byte", "trailing overlong", "truncated sequence"],
)
def test_invalid_bytes_after_a_valid_key_do_not_authenticate(value: bytes) -> None:
    assert status_for("test-key", value) == 401


def test_a_configured_replacement_character_does_not_match_an_invalid_byte() -> None:
    assert status_for("�", b"Bearer \xff") == 401


def test_the_header_name_is_matched_in_any_case() -> None:
    assert status_for("test-key", b"Bearer test-key", name=b"Authorization") == 200
    assert status_for("test-key", b"Bearer test-key", name=b"AUTHORIZATION") == 200


def test_a_utf16_encoded_header_name_is_not_authorization() -> None:
    name = "authorization".encode("utf-16-le")
    assert status_for("test-key", b"Bearer test-key", name=name) == 401


@pytest.mark.parametrize(
    "value",
    [
        b"Bearer test-key\xc2\xa0",
        b"Bearerx test-key",
        b"Bearer \ttest-key",
        b"Bearer \t test-key",
        b"\xc2\xa0Bearer test-key",
        b" test-key",
    ],
    ids=[
        "trailing NBSP",
        "scheme with extra letter",
        "space then tab",
        "space tab space",
        "leading NBSP before the scheme",
        "empty scheme",
    ],
)
def test_whitespace_and_scheme_variants_that_reach_the_app_get_401(value: bytes) -> None:
    assert status_for("test-key", value) == 401


@pytest.mark.parametrize("name", [b"x-authorization", b"proxy-authorization", b"authorization-x"])
def test_other_headers_are_not_treated_as_authorization(name: bytes) -> None:
    assert status_for("test-key", b"Bearer test-key", name=name) == 401


def test_a_key_with_an_internal_space_authenticates_only_with_that_space() -> None:
    assert status_for("a key", b"Bearer a key") == 200
    assert status_for("a key", b"Bearer akey") == 401


def test_a_utf8_key_sent_as_utf8_bytes_authenticates() -> None:
    assert status_for("clé-ü", "Bearer clé-ü".encode()) == 200


def test_a_key_configured_as_latin1_mojibake_does_not_match_the_real_utf8_bytes() -> None:
    # The old latin-1 reading turned the UTF-8 bytes of "clé-ü" into "clÃ©-Ã¼" and would have
    # accepted that configured key here.
    mojibake = "clé-ü".encode().decode("latin-1")
    assert status_for(mojibake, "Bearer clé-ü".encode()) == 401


def test_the_latin1_misreading_of_a_utf8_key_is_not_accepted() -> None:
    # The other direction: the key is "clé-ü" and the client sends what a latin-1 reader would
    # make of its UTF-8 bytes, re-encoded as UTF-8.
    misread = "clé-ü".encode().decode("latin-1").encode()
    assert status_for("clé-ü", b"Bearer " + misread) == 401


def test_a_leading_byte_order_mark_is_not_dropped() -> None:
    # UTF-8 BOM = EF BB BF. A decoder that drops it (utf-8-sig) would accept the first value.
    assert status_for("test-key", b"\xef\xbb\xbfBearer test-key") == 401
    assert status_for("test-key", b"Bearer \xef\xbb\xbftest-key") == 401


def test_a_differently_normalised_form_of_a_key_is_not_accepted() -> None:
    nfc = unicodedata.normalize("NFC", "clé-ü")
    nfd = unicodedata.normalize("NFD", "clé-ü")
    assert nfc != nfd
    assert status_for(nfc, f"Bearer {nfd}".encode()) == 401
    assert status_for(nfd, f"Bearer {nfc}".encode()) == 401


def make_request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers})


def test_authorization_values_decodes_utf8_and_escapes_invalid_bytes() -> None:
    request = make_request(
        [
            (b"authorization", b"Bearer \xff"),
            (b"x-other", b"Bearer z"),
            (b"Authorization", b"Bearer a"),
            (b"authorization", "Bearer clé".encode()),
        ]
    )
    assert authorization_values(request) == ["Bearer \udcff", "Bearer a", "Bearer clé"]


def test_authorization_values_is_empty_without_the_header() -> None:
    assert authorization_values(make_request([(b"x-other", b"Bearer z")])) == []
