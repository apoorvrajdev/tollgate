"""The ADR-0016 metric set, and the observer that feeds it from one finished request.

Every label value comes from a set the code or the route table fixes, never from the request:
the path is already mapped by the middleware, a provider name comes from a route target (which is
checked against the table), and `status` is the one label that takes its values on first use.
`method` is not a label: the request log carries it as received, so it is unbounded (T-402).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.observability.metrics import Counter, Histogram, MetricsRegistry
from app.observability.middleware import OTHER_PATH
from app.observability.record import RequestResult

CHAT_PATH = "/v1/chat/completions"
HEALTH_PATH = "/health"
METRICS_PATH = "/metrics"
# In seconds (ADR-0016). `+Inf` is implicit.
BUCKET_BOUNDS_SECONDS = (
    0.001,
    0.0025,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)
CACHE_VALUES = ("hit", "miss", "skip", "off")
ATTEMPT_OUTCOMES = (
    "ok",
    "connection",
    "timeout",
    "rate_limited",
    "upstream_status",
    "bad_response",
    "reply_too_large",
    "error",
)
LOOKUP_RESULTS = ("hit", "miss", "not_eligible", "embedder_failed")
OK_STATUS = 200


@dataclass(frozen=True, slots=True)
class RequestMetrics:
    registry: MetricsRegistry
    requests: Counter
    request_duration: Histogram
    chat_completions: Counter
    attempts: Counter
    attempt_duration: Histogram
    lookups: Counter
    lookup_duration: Histogram
    tokens_reserved: Counter
    tokens_charged: Counter
    settle_capped: Counter
    metrics_path: bool

    def observe(self, result: RequestResult) -> None:
        """Count one finished request. Never raises for a request the app itself served."""
        path = result.path
        if path == METRICS_PATH and not self.metrics_path:
            path = OTHER_PATH  # no such endpoint: the request was a 404 like any other path
        self.requests.inc({"path": path, "status": str(result.status)})
        self.request_duration.observe({"path": path}, result.duration_seconds)
        chat = result.chat
        if chat is None:
            return
        if result.status == OK_STATUS and chat.provider is not None:
            self.chat_completions.inc({"provider": chat.provider, "cache": chat.cache or "off"})
        for attempt in chat.attempts or ():
            labels = {"provider": attempt.provider_name}
            self.attempts.inc({**labels, "outcome": attempt.outcome})
            self.attempt_duration.observe(labels, attempt.duration_seconds)
        if chat.cache is not None:
            lookup = chat.cache if chat.cache != "skip" else chat.skip_reason
            if lookup is not None:
                self.lookups.inc({"result": lookup})
        if chat.lookup_duration_seconds is not None:
            self.lookup_duration.observe({}, chat.lookup_duration_seconds)
        if chat.reserved_tokens is not None:
            self.tokens_reserved.inc({}, chat.reserved_tokens)
        if chat.charged_tokens is not None:
            self.tokens_charged.inc({}, chat.charged_tokens)
        if chat.settle_capped:
            self.settle_capped.inc({})


def build_request_metrics(provider_names: Sequence[str], *, metrics_path: bool) -> RequestMetrics:
    """A new registry holding the whole set. `metrics_path` is true when `/metrics` is served."""
    providers = tuple(provider_names)
    paths = (CHAT_PATH, HEALTH_PATH, *((METRICS_PATH,) if metrics_path else ()), OTHER_PATH)
    registry = MetricsRegistry()
    buckets = BUCKET_BOUNDS_SECONDS
    return RequestMetrics(
        registry=registry,
        requests=registry.counter(
            "tollgate_http_requests_total",
            "HTTP requests answered, by path and status.",
            ("path", "status"),
            first_use_label="status",
            label_values={"path": paths},
        ),
        request_duration=registry.histogram(
            "tollgate_http_request_duration_seconds",
            "HTTP request duration in seconds, by path.",
            buckets,
            ("path",),
            label_sets=[{"path": path} for path in paths],
        ),
        chat_completions=registry.counter(
            "tollgate_chat_completions_total",
            "Chat completions answered with 200, by serving provider and cache result.",
            ("provider", "cache"),
            label_sets=[
                {"provider": name, "cache": cache} for name in providers for cache in CACHE_VALUES
            ],
        ),
        attempts=registry.counter(
            "tollgate_provider_attempts_total",
            "Provider calls, by provider and outcome.",
            ("provider", "outcome"),
            label_sets=[
                {"provider": name, "outcome": outcome}
                for name in providers
                for outcome in ATTEMPT_OUTCOMES
            ],
        ),
        attempt_duration=registry.histogram(
            "tollgate_provider_attempt_duration_seconds",
            "Provider call duration in seconds, by provider.",
            buckets,
            ("provider",),
            label_sets=[{"provider": name} for name in providers],
        ),
        lookups=registry.counter(
            "tollgate_cache_lookups_total",
            "Semantic cache lookups, by result.",
            ("result",),
            label_sets=[{"result": result} for result in LOOKUP_RESULTS],
        ),
        lookup_duration=registry.histogram(
            "tollgate_cache_lookup_duration_seconds",
            "Semantic cache lookup duration in seconds.",
            buckets,
        ),
        tokens_reserved=registry.counter(
            "tollgate_tokens_reserved_total", "Tokens reserved from the rate limiter."
        ),
        tokens_charged=registry.counter(
            "tollgate_tokens_charged_total", "Tokens charged to the rate limiter after a call."
        ),
        settle_capped=registry.counter(
            "tollgate_settle_capped_total", "Settles where the charge was capped at the capacity."
        ),
        metrics_path=metrics_path,
    )
