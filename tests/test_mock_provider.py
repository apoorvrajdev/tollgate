import asyncio

import pytest

from app.api.models import ChatRequest, ChatResponse
from app.providers.mock import REPLY_PREFIX, MockProvider, UuidIdSource, count_words
from tests.fakes import FakeClock, FixedIdSource


def make_request(*contents: str, model: str = "mock-1") -> ChatRequest:
    return ChatRequest.model_validate(
        {"model": model, "messages": [{"role": "user", "content": text} for text in contents]}
    )


def complete(
    request: ChatRequest, clock: FakeClock | None = None, response_id: str = "chatcmpl-test"
) -> ChatResponse:
    provider = MockProvider(clock or FakeClock(), FixedIdSource(response_id))
    return asyncio.run(provider.complete(request))


def test_usage_counts_words_across_messages_and_reply() -> None:
    # prompt: "a b c" + "d e" = 5 words; reply: "Mock reply: d e" = 4 words.
    usage = complete(make_request("a b c", "d e")).usage
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (5, 4, 9)


def test_name_field_is_not_counted_as_prompt_tokens() -> None:
    request = ChatRequest.model_validate(
        {
            "model": "mock-1",
            "messages": [{"role": "user", "content": "one", "name": "two words here"}],
        }
    )
    assert complete(request).usage.prompt_tokens == 1


def test_total_tokens_is_prompt_plus_completion() -> None:
    usage = complete(make_request("x y")).usage
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
    assert usage.prompt_tokens != usage.completion_tokens


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("", 0),
        ("   ", 0),
        ("one", 1),
        ("a  b", 2),
        ("a\tb\nc", 3),
        (" lead and trail ", 3),
    ],
)
def test_count_words_splits_on_any_whitespace_run(text: str, words: int) -> None:
    assert count_words(text) == words


def test_empty_prompt_counts_zero_prompt_tokens() -> None:
    usage = complete(make_request("")).usage
    assert (usage.prompt_tokens, usage.completion_tokens) == (0, 2)


def test_created_is_the_clock_time_floored_to_whole_seconds() -> None:
    assert complete(make_request("hi"), FakeClock(1_700_000_000.9)).created == 1_700_000_000


def test_created_follows_the_clock_when_it_advances() -> None:
    clock = FakeClock(100.0)
    first = complete(make_request("hi"), clock).created
    clock.advance(60)
    assert (first, complete(make_request("hi"), clock).created) == (100, 160)


def test_id_comes_from_the_injected_source() -> None:
    assert complete(make_request("hi"), response_id="chatcmpl-abc").id == "chatcmpl-abc"


def test_same_request_gives_the_same_response_under_a_fixed_clock_and_id() -> None:
    first = complete(make_request("hello there"), FakeClock(5.0))
    second = complete(make_request("hello there"), FakeClock(5.0))
    assert first == second


def test_choice_has_index_zero_assistant_role_and_stop() -> None:
    choice = complete(make_request("hi")).choices[0]
    assert (choice.index, choice.message.role, choice.finish_reason) == (0, "assistant", "stop")


def test_response_object_and_model_echo_the_request() -> None:
    response = complete(make_request("hi", model="some-model"))
    assert (response.object, response.model) == ("chat.completion", "some-model")


def test_reply_depends_on_the_last_message() -> None:
    assert complete(make_request("first", "second")).choices[0].message.content == (
        REPLY_PREFIX + "second"
    )
    assert complete(make_request("first", "other")).choices[0].message.content == (
        REPLY_PREFIX + "other"
    )


def test_exactly_one_choice_is_returned() -> None:
    assert len(complete(make_request("hi")).choices) == 1


def test_uuid_id_source_gives_distinct_prefixed_ids() -> None:
    source = UuidIdSource()
    first, second = source.next_id(), source.next_id()
    assert first != second
    assert first.startswith("chatcmpl-")
