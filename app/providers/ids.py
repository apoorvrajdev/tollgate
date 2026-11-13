"""Response ids, injected into the providers so a fixed source gives identical responses."""

import uuid
from typing import Protocol


class IdSource(Protocol):
    def next_id(self) -> str:
        """A response id, unique per call."""
        ...


class UuidIdSource:
    """Random ids for running the gateway. Tests inject a fixed source instead."""

    def next_id(self) -> str:
        return f"chatcmpl-{uuid.uuid4().hex}"
