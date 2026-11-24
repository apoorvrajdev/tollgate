"""The metrics registry and its Prometheus text format 0.0.4 output (T-403, ADR-0016).

Nothing here touches a clock or the network. The pinned multi-line strings are built from
`text()`, which ends each line with a line feed, and the special characters are built with
`chr`, so no escape sequence in this file can be mistaken for the character it names. Observed
values are binary-exact (0.25, 0.5, 1.0, ...), so every `_sum` is exact.
"""

import math
import re
from collections.abc import Sequence
from typing import Any

import pytest

from app.observability.metrics import (
    CONTENT_TYPE,
    Counter,
    Histogram,
    MetricsRegistry,
    format_number,
)

BS = chr(92)
QUOTE = chr(34)
LF = chr(10)
CR = chr(13)
E_ACUTE = chr(0xE9)
ARABIC_ONE = chr(0x661)


def text(*lines: str) -> str:
    return "".join(line + LF for line in lines)


# A small checker for the format's line grammar. `grammar_errors` is itself tested below.
BS_RE = BS + BS
NAME = "[a-zA-Z_:][a-zA-Z0-9_:]*"
HELP_TEXT = "(?:[^" + BS_RE + "]|" + BS_RE + BS_RE + "|" + BS_RE + "n)*"
LABEL_VALUE = QUOTE + "(?:[^" + QUOTE + BS_RE + "]|" + BS_RE + BS_RE
LABEL_VALUE += "|" + BS_RE + QUOTE + "|" + BS_RE + "n)*" + QUOTE
LABEL = "[a-zA-Z_][a-zA-Z0-9_]*=" + LABEL_VALUE
NUMBER = "-?[0-9]+(?:[.][0-9]+)?(?:e[+-]?[0-9]+)?|[+]Inf|-Inf|NaN"
HELP_LINE = re.compile("# HELP (" + NAME + ") (" + HELP_TEXT + ")")
TYPE_LINE = re.compile("# TYPE (" + NAME + ") (counter|histogram)")
SAMPLE_LINE = re.compile(
    "(" + NAME + ")(?:[{](" + LABEL + "(?:," + LABEL + ")*)?[}])? (" + NUMBER + ")"
)
HISTOGRAM_SUFFIXES = ("_bucket", "_sum", "_count")


def grammar_errors(rendered: str) -> list[str]:
    """Every way `rendered` breaks the line grammar, the one-HELP-and-one-TYPE rule, or the rule
    that TYPE comes before the first sample of its name."""
    errors: list[str] = []
    lines = rendered.split(LF)
    if lines[-1] == "":
        lines.pop()
    else:
        errors.append("no final line feed")
    kinds: dict[str, str] = {}
    helps: set[str] = set()
    for line in lines:
        if help_match := HELP_LINE.fullmatch(line):
            if help_match.group(1) in helps:
                errors.append("duplicate HELP: " + line)
            helps.add(help_match.group(1))
        elif type_match := TYPE_LINE.fullmatch(line):
            if type_match.group(1) in kinds:
                errors.append("duplicate TYPE: " + line)
            kinds[type_match.group(1)] = type_match.group(2)
        elif sample := SAMPLE_LINE.fullmatch(line):
            name = sample.group(1)
            family = name
            for suffix in HISTOGRAM_SUFFIXES:
                if name.endswith(suffix) and kinds.get(name[: -len(suffix)]) == "histogram":
                    family = name[: -len(suffix)]
            if family not in kinds:
                errors.append("sample before its TYPE: " + line)
        else:
            errors.append("not in the grammar: " + line)
    return errors


def one_counter(label_value: str, name: str = "m", help_text: str = "h") -> str:
    registry = MetricsRegistry()
    registry.counter(name, help_text, ("k",), label_sets=[{"k": label_value}])
    return registry.render()


def test_the_content_type_is_the_text_format_0_0_4_in_utf_8() -> None:
    assert CONTENT_TYPE == "text/plain; version=0.0.4; charset=utf-8"


def test_render_pins_the_exact_text_for_a_counter_and_a_histogram() -> None:
    registry = MetricsRegistry()
    jobs = registry.counter(
        "jobs_total", "Jobs done.", ("kind",), label_sets=[{"kind": "fast"}, {"kind": "slow"}]
    )
    seconds = registry.histogram(
        "job_seconds", "Job time.", (0.5, 1.0, 2.5), ("kind",), label_sets=[{"kind": "fast"}]
    )
    jobs.inc({"kind": "slow"}, 3)
    seconds.observe({"kind": "fast"}, 0.5)
    seconds.observe({"kind": "fast"}, 2.0)
    assert registry.render() == text(
        "# HELP jobs_total Jobs done.",
        "# TYPE jobs_total counter",
        'jobs_total{kind="fast"} 0',
        'jobs_total{kind="slow"} 3',
        "# HELP job_seconds Job time.",
        "# TYPE job_seconds histogram",
        'job_seconds_bucket{kind="fast",le="0.5"} 1',
        'job_seconds_bucket{kind="fast",le="1.0"} 1',
        'job_seconds_bucket{kind="fast",le="2.5"} 2',
        'job_seconds_bucket{kind="fast",le="+Inf"} 2',
        'job_seconds_sum{kind="fast"} 2.5',
        'job_seconds_count{kind="fast"} 2',
    )


def test_an_empty_registry_renders_the_empty_string() -> None:
    assert MetricsRegistry().render() == ""


def test_metrics_render_in_registration_order_not_name_order() -> None:
    registry = MetricsRegistry()
    registry.counter("zeta_total", "z")
    registry.counter("alpha_total", "a")
    registry.histogram("mid_seconds", "m", (1.0,))
    names = [line.split(" ")[2] for line in registry.render().split(LF) if "# TYPE" in line]
    assert names == ["zeta_total", "alpha_total", "mid_seconds"]


def test_help_escapes_the_backslash_and_the_line_feed_but_not_the_quote() -> None:
    help_text = "a" + BS + 'b"c' + LF + "d"
    expected = "a" + BS + BS + 'b"c' + BS + "nd"
    registry = MetricsRegistry()
    registry.counter("m", help_text)
    assert registry.render() == text("# HELP m " + expected, "# TYPE m counter", "m 0")


@pytest.mark.parametrize(
    ("value", "escaped"),
    [
        (BS, BS + BS),
        (QUOTE, BS + QUOTE),
        (LF, BS + "n"),
        (BS + QUOTE + LF, BS + BS + BS + QUOTE + BS + "n"),
        (QUOTE + BS, BS + QUOTE + BS + BS),
        ("a/b", "a/b"),
        (CR, CR),
        (E_ACUTE, E_ACUTE),
    ],
    ids=[
        "backslash",
        "quote",
        "line-feed",
        "all-three",
        "quote-then-backslash",
        "plain",
        "cr",
        "e",
    ],
)
def test_a_label_value_escapes_exactly_the_backslash_the_quote_and_the_line_feed(
    value: str, escaped: str
) -> None:
    assert one_counter(value).endswith('m{k="' + escaped + '"} 0' + LF)


def test_a_first_use_label_value_is_escaped() -> None:
    registry = MetricsRegistry()
    counter = registry.counter("m", "h", ("status",), first_use_label="status")
    counter.inc({"status": BS + QUOTE + LF})
    expected = BS + BS + BS + QUOTE + BS + "n"
    assert registry.render().endswith('m{status="' + expected + '"} 1' + LF)


def test_the_histogram_bucket_counts_a_value_equal_to_a_bound_in_that_bucket() -> None:
    for value, expected in [(0.5, [1, 1, 1]), (1.0, [0, 1, 1]), (2.0, [0, 0, 1])]:
        histogram = Histogram("h", "x", (0.5, 1.0, 2.0))
        histogram.observe({}, value)
        buckets = [int(line.rsplit(" ", 1)[1]) for line in histogram.lines() if "_bucket" in line]
        assert buckets == [*expected, 1]


def test_histogram_buckets_are_cumulative_and_the_inf_bucket_equals_the_count() -> None:
    histogram = Histogram("h", "x", (0.5, 1.0, 2.0))
    for value in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        histogram.observe({}, value)
    assert histogram.lines()[2:] == [
        'h_bucket{le="0.5"} 2',
        'h_bucket{le="1.0"} 4',
        'h_bucket{le="2.0"} 6',
        'h_bucket{le="+Inf"} 7',
        "h_sum 9.0",
        "h_count 7",
    ]


def test_a_value_above_every_bound_counts_only_in_inf_and_a_low_one_in_every_bucket() -> None:
    histogram = Histogram("h", "x", (1.0, 2.0))
    histogram.observe({}, 5.0)
    histogram.observe({}, -1.0)
    assert histogram.lines()[2:] == [
        'h_bucket{le="1.0"} 1',
        'h_bucket{le="2.0"} 1',
        'h_bucket{le="+Inf"} 2',
        "h_sum 4.0",
        "h_count 2",
    ]


def test_the_sum_is_a_float_written_with_repr_even_for_integer_observations() -> None:
    histogram = Histogram("h", "x", (1.0,))
    assert histogram.lines()[-2] == "h_sum 0.0"
    histogram.observe({}, 3)
    assert histogram.lines()[-2] == "h_sum 3.0"
    other = Histogram("h", "x", (1.0,))
    other.observe({}, 0.1)
    assert other.lines()[-2] == "h_sum 0.1"


def test_a_histogram_bound_is_written_as_a_float_even_when_given_an_int() -> None:
    histogram = Histogram("h", "x", (1, 60))
    assert 'h_bucket{le="1.0"} 0' in histogram.lines()
    assert 'h_bucket{le="60.0"} 0' in histogram.lines()


def test_a_declared_histogram_set_renders_zero_in_every_series_before_any_use() -> None:
    histogram = Histogram("h", "x", (0.5, 1.0), ("k",), label_sets=[{"k": "b"}, {"k": "a"}])
    assert histogram.lines()[2:] == [
        'h_bucket{k="b",le="0.5"} 0',
        'h_bucket{k="b",le="1.0"} 0',
        'h_bucket{k="b",le="+Inf"} 0',
        'h_sum{k="b"} 0.0',
        'h_count{k="b"} 0',
        'h_bucket{k="a",le="0.5"} 0',
        'h_bucket{k="a",le="1.0"} 0',
        'h_bucket{k="a",le="+Inf"} 0',
        'h_sum{k="a"} 0.0',
        'h_count{k="a"} 0',
    ]


def test_declared_counter_sets_render_zero_in_declaration_order_before_any_use() -> None:
    counter = Counter("m", "h", ("k",), label_sets=[{"k": "z"}, {"k": "a"}, {"k": "m"}])
    assert counter.lines()[2:] == ['m{k="z"} 0', 'm{k="a"} 0', 'm{k="m"} 0']


def test_an_unlabelled_counter_renders_zero_before_use() -> None:
    assert Counter("m", "h").lines()[2:] == ["m 0"]


def test_a_first_use_value_appears_only_after_its_first_increment() -> None:
    counter = Counter(
        "m", "h", ("path", "status"), first_use_label="status", label_values={"path": ("/a", "/b")}
    )
    assert counter.lines()[2:] == []
    counter.inc({"path": "/a", "status": "200"})
    assert counter.lines()[2:] == ['m{path="/a",status="200"} 1']


def test_first_use_series_are_grouped_by_the_declared_order_then_in_first_use_order() -> None:
    counter = Counter(
        "m", "h", ("path", "status"), first_use_label="status", label_values={"path": ("/a", "/b")}
    )
    for path, status in [("/b", "404"), ("/a", "200"), ("/b", "200"), ("/a", "404")]:
        counter.inc({"path": path, "status": status})
    assert counter.lines()[2:] == [
        'm{path="/a",status="200"} 1',
        'm{path="/a",status="404"} 1',
        'm{path="/b",status="404"} 1',
        'm{path="/b",status="200"} 1',
    ]


def test_a_counter_with_only_a_first_use_label_needs_no_other_values() -> None:
    counter = Counter("m", "h", ("status",), first_use_label="status")
    counter.inc({"status": "500"})
    counter.inc({"status": "200"})
    assert counter.lines()[2:] == ['m{status="500"} 1', 'm{status="200"} 1']


def test_inc_adds_ints_as_ints_and_floats_with_repr() -> None:
    counter = Counter("m", "h")
    counter.inc({})
    counter.inc({})
    assert counter.lines()[-1] == "m 2"
    counter.inc({}, 0.5)
    assert counter.lines()[-1] == "m 2.5"
    other = Counter("m", "h")
    other.inc({}, 2.0)
    assert other.lines()[-1] == "m 2.0"


def test_inc_accepts_zero_and_ignores_the_order_of_the_label_keys() -> None:
    counter = Counter("m", "h", ("a", "b"), label_sets=[{"a": "1", "b": "2"}])
    counter.inc({"b": "2", "a": "1"}, 0)
    counter.inc({"b": "2", "a": "1"})
    assert counter.lines()[-1] == 'm{a="1",b="2"} 1'


@pytest.mark.parametrize("amount", [-1, -0.5, -1e-9], ids=repr)
def test_inc_rejects_a_negative_amount_and_changes_nothing(amount: float) -> None:
    counter = Counter("m", "h")
    with pytest.raises(ValueError, match="negative"):
        counter.inc({}, amount)
    assert counter.lines()[-1] == "m 0"


@pytest.mark.parametrize("amount", [math.nan, math.inf, -math.inf], ids=repr)
def test_inc_rejects_a_non_finite_amount_and_changes_nothing(amount: float) -> None:
    counter = Counter("m", "h")
    with pytest.raises(ValueError, match="finite"):
        counter.inc({}, amount)
    assert counter.lines()[-1] == "m 0"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf], ids=repr)
def test_observe_rejects_a_non_finite_value_and_changes_nothing(value: float) -> None:
    histogram = Histogram("h", "x", (1.0,))
    with pytest.raises(ValueError, match="finite"):
        histogram.observe({}, value)
    assert histogram.lines()[-2:] == ["h_sum 0.0", "h_count 0"]


def test_a_rejected_first_use_inc_creates_no_series() -> None:
    counter = Counter("m", "h", ("status",), first_use_label="status")
    with pytest.raises(ValueError, match="negative"):
        counter.inc({"status": "new"}, -1)
    with pytest.raises(ValueError, match="finite"):
        counter.inc({"status": "new"}, math.nan)
    assert counter.lines()[2:] == []


BAD_LABELS: list[dict[str, Any]] = [
    {"kind": "other"},
    {},
    {"kind": "fast", "extra": "x"},
    {"other": "fast"},
    {"kind": 200},
    {"kind": None},
    {"kind": ["fast"]},
]
BAD_LABEL_IDS = [
    "unknown-value",
    "empty",
    "extra-key",
    "wrong-key",
    "int-value",
    "none-value",
    "list-value",
]


@pytest.mark.parametrize("labels", BAD_LABELS, ids=BAD_LABEL_IDS)
def test_a_counter_rejects_a_label_set_that_was_not_declared(labels: dict[str, Any]) -> None:
    counter = Counter("m", "h", ("kind",), label_sets=[{"kind": "fast"}])
    with pytest.raises(ValueError, match="label"):
        counter.inc(labels)
    assert counter.lines()[2:] == ['m{kind="fast"} 0']


@pytest.mark.parametrize("labels", BAD_LABELS, ids=BAD_LABEL_IDS)
def test_a_histogram_rejects_a_label_set_that_was_not_declared(labels: dict[str, Any]) -> None:
    histogram = Histogram("h", "x", (1.0,), ("kind",), label_sets=[{"kind": "fast"}])
    with pytest.raises(ValueError, match="label"):
        histogram.observe(labels, 0.5)
    assert histogram.lines()[-1] == 'h_count{kind="fast"} 0'


def test_an_unlabelled_metric_rejects_any_label() -> None:
    with pytest.raises(ValueError, match="label"):
        Counter("m", "h").inc({"k": "v"})
    with pytest.raises(ValueError, match="label"):
        Histogram("h", "x", (1.0,)).observe({"k": "v"}, 0.5)


def test_a_first_use_counter_rejects_an_undeclared_value_of_its_other_label() -> None:
    counter = Counter(
        "m", "h", ("path", "status"), first_use_label="status", label_values={"path": ("/a",)}
    )
    with pytest.raises(ValueError, match="not declared"):
        counter.inc({"path": "/nope", "status": "200"})
    assert counter.lines()[2:] == []
    counter.inc({"path": "/a", "status": "999"})
    assert counter.lines()[2:] == ['m{path="/a",status="999"} 1']


@pytest.mark.parametrize("labels", BAD_LABELS[1:], ids=BAD_LABEL_IDS[1:])
def test_a_first_use_counter_rejects_a_wrong_key_set(labels: dict[str, Any]) -> None:
    counter = Counter(
        "m", "h", ("path", "status"), first_use_label="status", label_values={"path": ("/a",)}
    )
    with pytest.raises(ValueError, match="label"):
        counter.inc(labels)


@pytest.mark.parametrize(
    "labels",
    [
        {"path": "/a", "status": 200},
        {"path": "/a", "status": ["200"]},
        {"path": 1, "status": "200"},
        {"path": ["/a"], "status": "200"},
        {"path": None, "status": "200"},
    ],
    ids=["int-status", "list-status", "int-path", "list-path", "none-path"],
)
def test_a_first_use_counter_rejects_a_non_string_value_with_the_right_keys(
    labels: dict[str, Any],
) -> None:
    counter = Counter(
        "m", "h", ("path", "status"), first_use_label="status", label_values={"path": ("/a",)}
    )
    with pytest.raises(ValueError, match="must be a string"):
        counter.inc(labels)
    assert counter.lines()[2:] == []


def test_the_registry_rejects_a_duplicate_name_across_counters_and_histograms() -> None:
    registry = MetricsRegistry()
    registry.counter("m", "h")
    with pytest.raises(ValueError, match="already registered"):
        registry.counter("m", "again")
    with pytest.raises(ValueError, match="already registered"):
        registry.histogram("m", "again", (1.0,))
    registry.histogram("h", "x", (1.0,))
    with pytest.raises(ValueError, match="already registered"):
        registry.counter("h", "again")


def test_a_rejected_registration_does_not_reserve_the_name() -> None:
    registry = MetricsRegistry()
    with pytest.raises(ValueError, match="label name"):
        registry.counter("m", "h", ("bad-name",))
    registry.counter("m", "h")
    assert "# TYPE m counter" in registry.render()


VALID_METRIC_NAMES = ["a", "_a", "a:b", "a1", ":a", "A"]
INVALID_METRIC_NAMES = ["", "1a", "a-b", "a b", "a" + LF, E_ACUTE, "a" + ARABIC_ONE, "a.b"]


@pytest.mark.parametrize("name", VALID_METRIC_NAMES)
def test_a_valid_metric_name_is_accepted(name: str) -> None:
    MetricsRegistry().counter(name, "h")
    MetricsRegistry().histogram(name, "h", (1.0,))


@pytest.mark.parametrize("name", INVALID_METRIC_NAMES, ids=repr)
def test_an_invalid_metric_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="metric name"):
        MetricsRegistry().counter(name, "h")
    with pytest.raises(ValueError, match="metric name"):
        MetricsRegistry().histogram(name, "h", (1.0,))


def labelled(label_name: str) -> Counter:
    return Counter("m", "h", (label_name,), label_sets=[{label_name: "v"}])


@pytest.mark.parametrize("name", ["a_1", "_x", "a__b", "A", "x1"])
def test_a_valid_label_name_is_accepted(name: str) -> None:
    labelled(name)


@pytest.mark.parametrize(
    "name", ["", "1a", "a-b", "a:b", "a" + LF, E_ACUTE, "a" + ARABIC_ONE], ids=repr
)
def test_an_invalid_label_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="label name"):
        labelled(name)
    with pytest.raises(ValueError, match="label name"):
        Histogram("h", "x", (1.0,), (name,), label_sets=[{name: "v"}])


@pytest.mark.parametrize("name", ["__x", "__", "___a"])
def test_a_label_name_starting_with_two_underscores_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        labelled(name)


@pytest.mark.parametrize("name", ["__x", "__"])
def test_a_histogram_label_name_starting_with_two_underscores_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        Histogram("h", "x", (1.0,), (name,), label_sets=[{name: "v"}])


def test_a_label_name_with_two_underscores_inside_or_one_at_the_start_is_accepted() -> None:
    labelled("a__b")
    labelled("_x")


def test_le_is_rejected_as_a_histogram_label_name_but_not_as_a_counter_one() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        Histogram("h", "x", (1.0,), ("le",), label_sets=[{"le": "v"}])
    labelled("le")
    Histogram("h", "x", (1.0,), ("Le",), label_sets=[{"Le": "v"}])
    Histogram("h", "x", (1.0,), ("le_",), label_sets=[{"le_": "v"}])


def test_the_constructors_reject_a_bad_declaration() -> None:
    with pytest.raises(ValueError, match="duplicate label name"):
        Counter("m", "h", ("a", "a"), label_sets=[{"a": "1"}])
    with pytest.raises(ValueError, match="label"):
        Counter("m", "h", ("a",), label_sets=[{"b": "1"}])
    with pytest.raises(ValueError, match="declare"):
        Counter("m", "h", ("a",))
    with pytest.raises(ValueError, match="declare"):
        Counter("m", "h", ("a",), label_sets=[])
    with pytest.raises(ValueError, match="no labels"):
        Counter("m", "h", label_sets=[{}])
    with pytest.raises(ValueError, match="duplicate label set"):
        Counter("m", "h", ("a",), label_sets=[{"a": "1"}, {"a": "1"}])
    with pytest.raises(ValueError, match="first-use"):
        Counter("m", "h", ("a",), label_sets=[{"a": "1"}], label_values={})
    with pytest.raises(ValueError, match="values, not label sets"):
        Counter("m", "h", ("a",), first_use_label="a", label_sets=[{"a": "1"}])
    with pytest.raises(ValueError, match="not one of"):
        Counter("m", "h", ("a",), first_use_label="b")
    with pytest.raises(ValueError, match="every other label"):
        Counter("m", "h", ("a", "b"), first_use_label="b")
    with pytest.raises(ValueError, match="every other label"):
        Counter("m", "h", ("a", "b"), first_use_label="b", label_values={"a": ("1",), "c": ("2",)})
    with pytest.raises(ValueError, match="distinct"):
        Counter("m", "h", ("a", "b"), first_use_label="b", label_values={"a": ()})
    with pytest.raises(ValueError, match="distinct"):
        Counter("m", "h", ("a", "b"), first_use_label="b", label_values={"a": ("1", "1")})


@pytest.mark.parametrize(
    "buckets",
    [(), (2.0, 1.0), (1.0, 1.0), (1.0, math.inf), (math.nan,), (-math.inf, 1.0)],
    ids=["empty", "descending", "duplicate", "inf", "nan", "minus-inf"],
)
def test_a_histogram_rejects_bad_bucket_bounds(buckets: Sequence[float]) -> None:
    with pytest.raises(ValueError, match="bucket"):
        Histogram("h", "x", buckets)


def test_label_sets_is_keyword_only_on_the_histogram_and_the_registry_like_the_counter() -> None:
    sets = [{"k": "a"}]
    with pytest.raises(TypeError):
        Histogram("h", "x", (1.0,), ("k",), sets)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        MetricsRegistry().histogram("h", "x", (1.0,), ("k",), sets)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Counter("m", "h", ("k",), sets)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        MetricsRegistry().counter("m", "h", ("k",), sets)  # type: ignore[call-arg]
    Histogram("h", "x", (1.0,), ("k",), label_sets=sets)
    MetricsRegistry().histogram("h", "x", (1.0,), ("k",), label_sets=sets)


def test_a_histogram_label_set_declaration_follows_the_counter_rules() -> None:
    with pytest.raises(ValueError, match="declare"):
        Histogram("h", "x", (1.0,), ("k",))
    with pytest.raises(ValueError, match="no labels"):
        Histogram("h", "x", (1.0,), (), label_sets=[{}])
    with pytest.raises(ValueError, match="duplicate label set"):
        Histogram("h", "x", (1.0,), ("k",), label_sets=[{"k": "a"}, {"k": "a"}])


@pytest.mark.parametrize(
    ("value", "written"),
    [
        (0, "0"),
        (7, "7"),
        (2.0, "2.0"),
        (0.1, "0.1"),
        (1e16, "1e+16"),
        (math.inf, "+Inf"),
        (-math.inf, "-Inf"),
        (math.nan, "NaN"),
    ],
)
def test_format_number_writes_ints_as_ints_floats_with_repr_and_infinity_as_inf(
    value: float, written: str
) -> None:
    assert format_number(value) == written


def several_metrics() -> MetricsRegistry:
    registry = MetricsRegistry()
    registry.counter("plain_total", "A plain counter.")
    labelled_counter = registry.counter(
        "labelled_total",
        "Help with " + BS + " and a" + LF + "line feed and a " + QUOTE + ".",
        ("k",),
        label_sets=[{"k": BS + QUOTE + LF}, {"k": "plain"}],
    )
    first_use = registry.counter(
        "http_total", "First use.", ("path", "status"), first_use_label="status",
        label_values={"path": ("/a", "/b")},
    )  # fmt: skip
    seconds = registry.histogram("a_seconds", "Plain histogram.", (0.5, 1.0))
    by_kind = registry.histogram(
        "b_seconds",
        "By kind.",
        (0.25, 1.0, 5.0),
        ("kind",),
        label_sets=[{"kind": "x"}, {"kind": QUOTE}],
    )
    labelled_counter.inc({"k": "plain"}, 2)
    first_use.inc({"path": "/b", "status": "404"})
    seconds.observe({}, 0.75)
    by_kind.observe({"kind": QUOTE}, 0.25)
    return registry


def test_every_line_of_a_registry_with_several_metrics_is_in_the_grammar() -> None:
    rendered = several_metrics().render()
    assert grammar_errors(rendered) == []
    assert "_created" not in rendered
    assert rendered.count("# TYPE ") == 5
    assert rendered.endswith(LF)
    assert not rendered.endswith(LF + LF)


def test_the_grammar_checker_accepts_a_valid_text_and_finds_each_kind_of_fault() -> None:
    valid = text("# HELP a h", "# TYPE a counter", 'a{k="x"} 1')
    assert grammar_errors(valid) == []
    histogram = text("# HELP h x", "# TYPE h histogram", 'h_bucket{le="+Inf"} 0', "h_sum 0.0")
    assert grammar_errors(histogram + "h_count 0" + LF) == []
    faults = {
        "type after sample": text("# HELP a h", "a 1", "# TYPE a counter"),
        "unescaped quote": text("# HELP a h", "# TYPE a counter", 'a{k="x"y"} 1'),
        "lone backslash in value": text("# HELP a h", "# TYPE a counter", 'a{k="x' + BS + 'y"} 1'),
        "lone backslash in help": text("# HELP a x" + BS + "y", "# TYPE a counter"),
        "no final line feed": valid[:-1],
        "duplicate type": valid + text("# TYPE a counter"),
        "duplicate help": valid + text("# HELP a h"),
        "unknown sample name": text("# HELP a h", "# TYPE a counter", "b 1"),
        "bucket of a counter": text("# HELP a h", "# TYPE a counter", "a_bucket 1"),
        "bad number": text("# HELP a h", "# TYPE a counter", "a one"),
        "blank line": valid + LF,
    }
    for name, rendered in faults.items():
        assert grammar_errors(rendered) != [], name
