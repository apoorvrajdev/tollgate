"""Authorization header cases shared by the authenticator tests and the route tests."""

EXPECTED_401_BODY = {
    "error": {
        "message": "Missing or invalid API key. Send it as 'Authorization: Bearer <key>'.",
        "type": "invalid_request_error",
        "param": None,
        "code": "invalid_api_key",
    }
}

# Header values (one string per Authorization header) that must be rejected when the only
# configured key is "test-key".
REJECTED_HEADER_VALUES: dict[str, list[str]] = {
    "no header": [],
    "basic scheme": ["Basic dGVzdA=="],
    "token scheme": ["Token test-key"],
    "key without scheme": ["test-key"],
    "scheme only": ["Bearer"],
    "scheme and one space": ["Bearer "],
    "scheme and many spaces": ["Bearer     "],
    "empty value": [""],
    "key plus extra word": ["Bearer test-key extra"],
    "tab instead of space": ["Bearer\ttest-key"],
    # A real server strips a trailing tab before the app sees it (h11 does); this is the app's own
    # rule for a value that does reach it.
    "trailing tab": ["Bearer test-key\t"],
    "byte order mark before the scheme": ["\ufeffBearer test-key"],
    "byte order mark before the key": ["Bearer \ufefftest-key"],
    "tab only token": ["Bearer \t"],
    "space then tab before the key": ["Bearer \ttest-key"],
    "space tab space before the key": ["Bearer \t test-key"],
    "trailing non-breaking space": ["Bearer test-key\xa0"],
    "scheme with an extra letter": ["Bearerx test-key"],
    "non-breaking space padding": ["Bearer \xa0test-key"],
    "wrong key": ["Bearer wrong"],
    "prefix of the key": ["Bearer test-ke"],
    "key plus one character": ["Bearer test-keyx"],
    "key in other case": ["Bearer TEST-KEY"],
    "duplicate valid headers": ["Bearer test-key", "Bearer test-key"],
    "wrong then valid": ["Bearer wrong", "Bearer test-key"],
    "valid then wrong": ["Bearer test-key", "Bearer wrong"],
    "non-latin1 range characters": ["Bearer \x80\xff"],
    "lone surrogate": ["Bearer \ud800"],
    "very long key": ["Bearer " + "x" * 100_000],
}

# Header values that must authenticate the key "test-key".
ACCEPTED_HEADER_VALUES: dict[str, str] = {
    "canonical": "Bearer test-key",
    "lowercase scheme": "bearer test-key",
    "uppercase scheme": "BEARER test-key",
    "two spaces": "Bearer  test-key",
    "trailing space": "Bearer test-key ",
}
