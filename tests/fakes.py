"""Test doubles shared across tests."""

from app.api.models import ChatRequest, ChatResponse, Choice, ResponseMessage, Usage
from app.settings import Settings


class FakeClock:
    """A clock that moves only when advance() is called."""

    def __init__(self, start_seconds: float = 0.0) -> None:
        self._now_seconds = start_seconds

    def now_seconds(self) -> float:
        return self._now_seconds

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("advance seconds must not be negative")
        self._now_seconds += seconds


class FixedIdSource:
    """An id source that always returns the same id, so responses are identical across calls."""

    def __init__(self, response_id: str = "chatcmpl-test") -> None:
        self._response_id = response_id

    def next_id(self) -> str:
        return self._response_id


class ScriptedProvider:
    """A provider that records each request, then raises `error` or answers with fixed values.

    It reports `reported_model`, never the model it was sent, so a test can tell the two apart.
    Every call appends `name` to `log`, which several providers can share to record call order.
    """

    def __init__(
        self,
        name: str,
        *,
        error: Exception | None = None,
        reported_model: str = "reported",
        prompt_tokens: int = 20,
        completion_tokens: int = 17,
        log: list[str] | None = None,
    ) -> None:
        self.name = name
        self.requests: list[ChatRequest] = []
        self._error = error
        self._reported_model = reported_model
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._log = log if log is not None else []

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        self._log.append(self.name)
        if self._error is not None:
            raise self._error
        return ChatResponse(
            id=f"chatcmpl-{self.name}",
            object="chat.completion",
            created=0,
            model=self._reported_model,
            choices=[
                Choice(
                    index=0,
                    message=ResponseMessage(role="assistant", content=f"reply from {self.name}"),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                total_tokens=self._prompt_tokens + self._completion_tokens,
            ),
        )


class FakeClient:
    """A closable client that records each close in `log`, then raises `error` if one is set.

    The close is logged before it raises, so a test sees that a failing close was attempted.
    """

    def __init__(self, name: str, *, log: list[str], error: Exception | None = None) -> None:
        self.name = name
        self.closes = 0
        self._log = log
        self._error = error

    async def aclose(self) -> None:
        self.closes += 1
        self._log.append(self.name)
        if self._error is not None:
            raise self._error


TEST_API_KEY = "test-key"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_KEY}"}


def make_settings(**overrides: str) -> Settings:
    """Settings built from an explicit mapping, so tests never depend on the process environment."""
    environ = {"TOLLGATE_API_KEYS": TEST_API_KEY, "TOLLGATE_TOKENS_PER_MINUTE": "1000"}
    environ.update(overrides)
    return Settings.from_env(environ)
