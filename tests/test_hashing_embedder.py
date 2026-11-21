"""The embedder interface's error and the hashing baseline (ADR-0015, T-301)."""

import asyncio
import math
from array import array

import pytest

from app.cache.embedder import Embedder, EmbeddingError
from app.cache.hashing import HashingEmbedder
from app.providers.errors import ProviderError, ProviderErrorKind

# "Banana" lower-cased and padded is " banana ": the windows " ba", "ban", "ana", "nan", "ana" and
# "na ". Computed from that description, not by the module under test: for each window w, count
# int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "big") % 512.
PINNED_INPUT = "Banana"
PINNED_COUNTS = {60: 2, 136: 1, 198: 1, 441: 1, 504: 1}


def embed(text: str, embedder: HashingEmbedder | None = None) -> array[float]:
    return asyncio.run((embedder or HashingEmbedder()).embed(text))


def non_zero(vector: array[float]) -> dict[int, float]:
    return {index: value for index, value in enumerate(vector) if value}


def norm(vector: array[float]) -> float:
    return math.sqrt(math.sumprod(vector, vector))


@pytest.mark.parametrize(
    ("kind", "status", "message"),
    [
        ("bad_response", None, "embedding failed: bad_response"),
        ("upstream_status", 404, "embedding failed: upstream_status (HTTP 404)"),
        ("timeout", None, "embedding failed: timeout"),
        ("bad_response", 201, "embedding failed: bad_response (HTTP 201)"),
    ],
)
def test_embedding_error_message_holds_only_the_kind_and_the_status(
    kind: ProviderErrorKind, status: int | None, message: str
) -> None:
    error = EmbeddingError(kind, status)
    assert str(error) == message
    assert (error.kind, error.status_code) == (kind, status)
    assert not isinstance(error, ProviderError)


def test_the_hashing_embedder_identity_is_hashing_v1() -> None:
    embedder: Embedder = HashingEmbedder()
    assert embedder.identity == "hashing:v1"


@pytest.mark.parametrize(
    "text",
    ["a", PINNED_INPUT, "Hello, World!", "café 你好", "the quick brown fox " * 100],
    ids=["one-char", "pinned", "punctuation", "non-ascii", "2000-chars"],
)
def test_embed_returns_a_double_array_of_512_with_unit_norm(text: str) -> None:
    vector = embed(text)
    assert isinstance(vector, array)
    assert vector.typecode == "d"
    assert len(vector) == 512
    assert abs(norm(vector) - 1.0) <= 1e-12


def test_one_fixed_input_gives_the_pinned_indices_and_counts() -> None:
    total = math.sqrt(sum(count * count for count in PINNED_COUNTS.values()))
    expected = {index: count / total for index, count in PINNED_COUNTS.items()}
    assert non_zero(embed(PINNED_INPUT)) == expected


def test_the_same_text_gives_the_same_vector_from_two_instances() -> None:
    first = embed("what is a token bucket?", HashingEmbedder())
    second = embed("what is a token bucket?", HashingEmbedder())
    assert list(first) == list(second)


@pytest.mark.parametrize(
    ("upper", "lower"),
    [("HELLO World", "hello world"), ("ÉCOLE", "école")],
    ids=["ascii", "accented"],
)
def test_upper_and_lower_case_give_the_same_vector(upper: str, lower: str) -> None:
    assert list(embed(upper)) == list(embed(lower))


def test_two_different_texts_give_different_vectors() -> None:
    assert list(embed("hello world")) != list(embed("hello there"))


def test_a_single_character_gives_one_window() -> None:
    assert list(non_zero(embed("a")).values()) == [1.0]


def test_the_empty_string_raises_a_bad_response_with_no_status() -> None:
    with pytest.raises(EmbeddingError) as raised:
        embed("")
    error = raised.value
    assert (error.kind, error.status_code) == ("bad_response", None)
    assert str(error) == "embedding failed: bad_response"
    assert error.__context__ is None
    assert error.__cause__ is None


def test_lower_case_is_not_case_folding() -> None:
    # str.casefold() maps the sharp s to "ss"; str.lower() keeps it.
    assert list(embed("straße")) != list(embed("strasse"))


def test_a_lone_surrogate_is_hashed_without_raising() -> None:
    vector = embed("a\ud800")
    assert abs(norm(vector) - 1.0) <= 1e-12
    assert list(vector) != list(embed("a"))
