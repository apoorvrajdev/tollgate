"""Request and response models for POST /v1/chat/completions (ADR-0004, ADR-0008).

Request and response models are separate classes so the OpenAPI document keeps one schema per
model. Parameters the gateway does not support are rejected with the custom error type
"unsupported_parameter", which the error handler maps to the ADR-0008 code of the same name.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

UNSUPPORTED_PARAMETER = "unsupported_parameter"


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    name: str | None = None

    @field_validator("content", mode="before")
    @classmethod
    def reject_array_content(cls, value: Any) -> Any:
        if isinstance(value, list):
            raise PydanticCustomError(
                UNSUPPORTED_PARAMETER, "Array content is not supported; send content as a string"
            )
        return value

    @field_validator("content")
    @classmethod
    def reject_text_that_cannot_be_encoded(cls, value: str) -> str:
        # A lone surrogate (JSON "\ud800") parses, but cannot be written back as UTF-8 JSON, so the
        # response would fail with a 500.
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise PydanticCustomError(
                "invalid_text", "Content must be valid Unicode text"
            ) from None
        return value


class ChatRequest(BaseModel):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    n: int | None = Field(default=None, ge=1)
    stream: bool | None = None
    user: str | None = None

    @field_validator("n")
    @classmethod
    def reject_more_than_one_choice(cls, value: int | None) -> int | None:
        if value is not None and value > 1:
            raise PydanticCustomError(UNSUPPORTED_PARAMETER, "Only n=1 is supported")
        return value

    @field_validator("stream")
    @classmethod
    def reject_streaming(cls, value: bool | None) -> bool | None:
        if value is True:
            raise PydanticCustomError(UNSUPPORTED_PARAMETER, "Streaming is not supported")
        return value


class ResponseMessage(BaseModel):
    role: Literal["assistant"]
    content: str


class Choice(BaseModel):
    index: int
    message: ResponseMessage
    finish_reason: Literal["stop", "length", "content_filter"]


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: list[Choice]
    usage: Usage
