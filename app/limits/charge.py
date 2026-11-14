"""The tokens a served request settles: the provider's count, capped at the bucket capacity.

One request never charges more than one full bucket, so an absurd usage count from a provider
empties the bucket but cannot lock the caller's key out (ADR-0012). A negative count is returned
unchanged, so `settle` still rejects it (ADR-0010).
"""


def charged_tokens(reported_tokens: int, limit_tokens: int) -> int:
    """The smaller of the reported count and the limit; a negative count is not clamped."""
    return reported_tokens if reported_tokens <= limit_tokens else limit_tokens
