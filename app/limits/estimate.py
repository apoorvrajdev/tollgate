"""How many tokens to reserve for a chat request (ADR-0007).

The estimate is a character-count heuristic behind the TokenEstimator protocol, so a real
tokenizer can replace it through a later ADR. It is rough, mostly right for English text, and
the provider's reported usage corrects it when the reservation is settled.
"""

from typing import Protocol

from app.api.models import ChatRequest

# The OpenAI cookbook's per-message overhead (ADR-0007) applied to a character count.
CHARACTERS_PER_TOKEN = 4
TOKENS_PER_MESSAGE = 3
TOKENS_PER_NAME = 1
TOKENS_PER_REPLY = 3


class TokenEstimator(Protocol):
    def estimate_input_tokens(self, request: ChatRequest) -> int:
        """Estimated prompt tokens for the request, including the reply overhead."""
        ...


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


class HeuristicEstimator:
    """ceil(characters / 4) + 3 per message, +1 per message with a name, +3 for the reply.

    Characters are Python string length, so a character outside the BMP counts once and a base
    letter plus a combining mark counts twice. A `name` counts whenever it is present, even if it
    is an empty string. The role does not count.
    """

    def estimate_input_tokens(self, request: ChatRequest) -> int:
        total_tokens = TOKENS_PER_REPLY
        for message in request.messages:
            total_tokens += _ceil_div(len(message.content), CHARACTERS_PER_TOKEN)
            total_tokens += TOKENS_PER_MESSAGE
            if message.name is not None:
                total_tokens += TOKENS_PER_NAME
        return total_tokens


def reserved_tokens(request: ChatRequest, estimator: TokenEstimator) -> int:
    """The estimate plus the completion allowance, to reserve before calling the provider.

    The allowance is `max_completion_tokens` if given, else `max_tokens`, else 0. When both are
    given, `max_completion_tokens` wins and `max_tokens` is ignored.
    """
    estimated_tokens = estimator.estimate_input_tokens(request)
    if request.max_completion_tokens is not None:
        return estimated_tokens + request.max_completion_tokens
    if request.max_tokens is not None:
        return estimated_tokens + request.max_tokens
    return estimated_tokens
