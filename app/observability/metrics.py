"""A small metrics registry that writes Prometheus text format 0.0.4 (ADR-0016), with no dependency.

A `MetricsRegistry` creates its counters and histograms, so a metric is never left unregistered, and
`render()` writes them in registration order. Every label set is declared when the metric is built,
and is written at 0 before it is first used. One counter label may instead take its values on first
use (ADR-0016 does this for `status` only); the counter then declares the allowed values of each of
its other labels, and a combination is written only once it has been used. A label set or a label
value that was not declared is rejected, so the series count is bounded by the code, never by the
caller. A bad name, label or value is rejected with a `ValueError` (an int too large for a float
raises `OverflowError` instead); a rejected call changes nothing.

The format rules (prometheus.io/docs/instrumenting/exposition_formats/): UTF-8 with `\\n` line
endings and a final line feed; HELP text escapes the backslash and the line feed; a label value
escapes the backslash, the double quote and the line feed, the backslash first; TYPE comes before
the first sample of its name; a histogram writes cumulative `_bucket{le="..."}` series ending in
`le="+Inf"`, which equals `_count`, then `_sum` and `_count`. No `_created` series is written.
Integers are written as integers and floats with `repr`. A bucket bound is always a float, so it is
written as `1.0`, not `1`.

There is no locking: the app runs on one event loop, and no method awaits.
"""

import math
import re
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import accumulate, pairwise, product

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
BACKSLASH = chr(92)
QUOTE = chr(34)
LINE_FEED = chr(10)
INF_LABEL_VALUE = "+Inf"
# `fullmatch` with explicit ASCII ranges: no trailing line feed, no Unicode letters or digits.
METRIC_NAME_PATTERN = re.compile("[a-zA-Z_:][a-zA-Z0-9_:]*")
LABEL_NAME_PATTERN = re.compile("[a-zA-Z_][a-zA-Z0-9_]*")
RESERVED_LABEL_PREFIX = "__"
HISTOGRAM_BUCKET_LABEL = "le"

type Number = int | float
type LabelValues = tuple[str, ...]


def escape_help(text: str) -> str:
    return text.replace(BACKSLASH, BACKSLASH * 2).replace(LINE_FEED, BACKSLASH + "n")


def escape_label_value(text: str) -> str:
    escaped = text.replace(BACKSLASH, BACKSLASH * 2)
    return escaped.replace(QUOTE, BACKSLASH + QUOTE).replace(LINE_FEED, BACKSLASH + "n")


def format_number(value: Number) -> str:
    """An int as an int, infinity as `+Inf` or `-Inf`, and any other float with `repr`."""
    if isinstance(value, int):
        return str(value)
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return INF_LABEL_VALUE if value > 0 else "-Inf"
    return repr(value)


def check_metric_name(name: str) -> None:
    if METRIC_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError(f"invalid metric name: {name!r}")


def check_label_names(label_names: Sequence[str], *, reserved: frozenset[str]) -> None:
    for label_name in label_names:
        if LABEL_NAME_PATTERN.fullmatch(label_name) is None:
            raise ValueError(f"invalid label name: {label_name!r}")
        if label_name.startswith(RESERVED_LABEL_PREFIX):
            raise ValueError(f"label name is reserved: {label_name!r}")
        if label_name in reserved:
            raise ValueError(f"label name is not allowed on this metric: {label_name!r}")
    if len(set(label_names)) != len(label_names):
        raise ValueError("duplicate label name")


def label_text(pairs: Sequence[tuple[str, str]]) -> str:
    if not pairs:
        return ""
    body = ",".join(f"{name}={QUOTE}{escape_label_value(value)}{QUOTE}" for name, value in pairs)
    return "{" + body + "}"


def sample_line(name: str, pairs: Sequence[tuple[str, str]], value: Number) -> str:
    return f"{name}{label_text(pairs)} {format_number(value)}"


def header_lines(name: str, help_text: str, kind: str) -> list[str]:
    return [f"# HELP {name} {escape_help(help_text)}", f"# TYPE {name} {kind}"]


def declared_key(
    label_names: tuple[str, ...], labels: Mapping[str, str], declared: frozenset[LabelValues]
) -> LabelValues:
    """The label values in `label_names` order, if `labels` is exactly one declared set."""
    key = exact_key(label_names, labels)
    if key not in declared:
        raise ValueError("label set was not declared")
    return key


def exact_key(label_names: tuple[str, ...], labels: Mapping[str, str]) -> LabelValues:
    if set(labels) != set(label_names):
        raise ValueError("labels do not match the declared label names")
    values = tuple(labels[name] for name in label_names)
    if not all(isinstance(value, str) for value in values):
        raise ValueError("a label value must be a string")
    return values


def declare_sets(
    label_names: tuple[str, ...], label_sets: Sequence[Mapping[str, str]] | None
) -> tuple[LabelValues, ...]:
    """The declared label sets as value tuples, in declaration order."""
    if not label_names:
        if label_sets is not None:
            raise ValueError("label sets were given for a metric with no labels")
        return ((),)
    if not label_sets:
        raise ValueError("a labelled metric must declare its label sets")
    keys = tuple(exact_key(label_names, label_set) for label_set in label_sets)
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate label set")
    return keys


class Counter:
    """A monotonic count per label set. See the module docstring for the declaration rules."""

    kind = "counter"

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: Sequence[str] = (),
        *,
        label_sets: Sequence[Mapping[str, str]] | None = None,
        first_use_label: str | None = None,
        label_values: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        check_metric_name(name)
        names = tuple(label_names)
        check_label_names(names, reserved=frozenset())
        self.name = name
        self.help_text = help_text
        self._label_names = names
        self._first_use_label = first_use_label
        self._values: dict[LabelValues, Number] = {}
        self._combinations: dict[LabelValues, int] = {}
        self._declared: frozenset[LabelValues] = frozenset()
        if first_use_label is None:
            if label_values is not None:
                raise ValueError("label values are for a counter with a first-use label")
            keys = declare_sets(names, label_sets)
            self._values = dict.fromkeys(keys, 0)
            self._declared = frozenset(keys)
        else:
            self._declare_first_use(label_sets, label_values)

    def _declare_first_use(
        self,
        label_sets: Sequence[Mapping[str, str]] | None,
        label_values: Mapping[str, Sequence[str]] | None,
    ) -> None:
        if label_sets is not None:
            raise ValueError("a counter with a first-use label declares values, not label sets")
        if self._first_use_label not in self._label_names:
            raise ValueError("the first-use label is not one of the label names")
        others = tuple(name for name in self._label_names if name != self._first_use_label)
        given = label_values if label_values is not None else {}
        if set(given) != set(others):
            raise ValueError("label values must be declared for every other label")
        if any(not values or len(set(values)) != len(values) for values in given.values()):
            raise ValueError("each label needs one or more distinct declared values")
        combinations = product(*(tuple(given[name]) for name in others))
        self._combinations = {combination: index for index, combination in enumerate(combinations)}

    def _combination_of(self, key: LabelValues) -> LabelValues:
        return tuple(
            value
            for name, value in zip(self._label_names, key, strict=True)
            if name != self._first_use_label
        )

    def inc(self, labels: Mapping[str, str], amount: Number = 1) -> None:
        if self._first_use_label is None:
            key = declared_key(self._label_names, labels, self._declared)
        else:
            key = exact_key(self._label_names, labels)
            if self._combination_of(key) not in self._combinations:
                raise ValueError("label value was not declared")
        if not math.isfinite(amount):
            raise ValueError("amount must be finite")
        if amount < 0:
            raise ValueError("amount must not be negative")
        self._values[key] = self._values.get(key, 0) + amount

    def lines(self) -> list[str]:
        keys = list(self._values)
        if self._first_use_label is not None:  # stable: first-use order inside a combination
            keys.sort(key=lambda key: self._combinations[self._combination_of(key)])
        lines = header_lines(self.name, self.help_text, self.kind)
        for key in keys:
            pairs = list(zip(self._label_names, key, strict=True))
            lines.append(sample_line(self.name, pairs, self._values[key]))
        return lines


@dataclass(slots=True)
class _Series:
    bucket_counts: list[int]  # per bucket, not cumulative
    count: int = 0
    total: float = 0.0


class Histogram:
    """Observations in fixed ascending buckets, per declared label set."""

    kind = "histogram"

    def __init__(
        self,
        name: str,
        help_text: str,
        buckets: Sequence[float],
        label_names: Sequence[str] = (),
        label_sets: Sequence[Mapping[str, str]] | None = None,
    ) -> None:
        check_metric_name(name)
        names = tuple(label_names)
        check_label_names(names, reserved=frozenset({HISTOGRAM_BUCKET_LABEL}))
        bounds = tuple(float(bound) for bound in buckets)
        if not bounds or not all(math.isfinite(bound) for bound in bounds):
            raise ValueError("buckets must be one or more finite bounds")
        if any(low >= high for low, high in pairwise(bounds)):
            raise ValueError("buckets must be strictly ascending")
        self.name = name
        self.help_text = help_text
        self._label_names = names
        self._bounds = bounds
        keys = declare_sets(names, label_sets)
        self._declared = frozenset(keys)
        self._series = {key: _Series([0] * len(bounds)) for key in keys}

    def observe(self, labels: Mapping[str, str], seconds: float) -> None:
        key = declared_key(self._label_names, labels, self._declared)
        if not math.isfinite(seconds):
            raise ValueError("observed value must be finite")
        series = self._series[key]
        index = bisect_left(self._bounds, seconds)  # a value equal to a bound is in its bucket
        if index < len(self._bounds):
            series.bucket_counts[index] += 1
        series.count += 1
        series.total += seconds

    def lines(self) -> list[str]:
        lines = header_lines(self.name, self.help_text, self.kind)
        for key, series in self._series.items():
            pairs = list(zip(self._label_names, key, strict=True))
            cumulative = accumulate(series.bucket_counts)
            for bound, in_bucket in zip(self._bounds, cumulative, strict=True):
                bucket_pairs = [*pairs, (HISTOGRAM_BUCKET_LABEL, format_number(bound))]
                lines.append(sample_line(f"{self.name}_bucket", bucket_pairs, in_bucket))
            inf_pairs = [*pairs, (HISTOGRAM_BUCKET_LABEL, INF_LABEL_VALUE)]
            lines.append(sample_line(f"{self.name}_bucket", inf_pairs, series.count))
            lines.append(sample_line(f"{self.name}_sum", pairs, series.total))
            lines.append(sample_line(f"{self.name}_count", pairs, series.count))
        return lines


class MetricsRegistry:
    def __init__(self) -> None:
        self._metrics: dict[str, Counter | Histogram] = {}

    def counter(
        self,
        name: str,
        help_text: str,
        label_names: Sequence[str] = (),
        *,
        label_sets: Sequence[Mapping[str, str]] | None = None,
        first_use_label: str | None = None,
        label_values: Mapping[str, Sequence[str]] | None = None,
    ) -> Counter:
        metric = Counter(
            name,
            help_text,
            label_names,
            label_sets=label_sets,
            first_use_label=first_use_label,
            label_values=label_values,
        )
        self._register(metric)
        return metric

    def histogram(
        self,
        name: str,
        help_text: str,
        buckets: Sequence[float],
        label_names: Sequence[str] = (),
        label_sets: Sequence[Mapping[str, str]] | None = None,
    ) -> Histogram:
        metric = Histogram(name, help_text, buckets, label_names, label_sets)
        self._register(metric)
        return metric

    def _register(self, metric: Counter | Histogram) -> None:
        if metric.name in self._metrics:
            raise ValueError(f"metric name is already registered: {metric.name}")
        self._metrics[metric.name] = metric

    def render(self) -> str:
        """The text format: every line ends in a line feed, so the text ends in one."""
        lines = [line for metric in self._metrics.values() for line in metric.lines()]
        return "".join(line + LINE_FEED for line in lines)
