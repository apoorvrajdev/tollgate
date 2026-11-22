"""The cache eval dataset file (T-304, AC1). Parsed with the standard library only, so these
checks do not depend on the loader under test."""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DATASET_PATH = Path(__file__).resolve().parent.parent / "eval" / "cache_pairs.json"
DIFFERENT_CATEGORIES = [
    "unrelated_topic",
    "negation",
    "changed_number",
    "swapped_order",
    "changed_entity",
]
SAME_CATEGORIES = ["synonym", "word_order", "register", "question_vs_request", "concise_vs_verbose"]
KEYS = {"id", "label", "category", "first", "second"}


def pairs() -> list[dict[str, Any]]:
    data = json.loads(DATASET_PATH.read_bytes())
    assert isinstance(data, list)
    return data


def test_dataset_has_80_pairs_40_same_40_different_8_per_category() -> None:
    loaded = pairs()
    assert len(loaded) == 80
    assert Counter(pair["label"] for pair in loaded) == {"same": 40, "different": 40}
    different = Counter(pair["category"] for pair in loaded if pair["label"] == "different")
    assert different == dict.fromkeys(DIFFERENT_CATEGORIES, 8)
    same = Counter(pair["category"] for pair in loaded if pair["label"] == "same")
    assert same == dict.fromkeys(SAME_CATEGORIES, 8)


def test_dataset_ids_are_unique_and_match_their_label_or_category() -> None:
    loaded = pairs()
    ids = [pair["id"] for pair in loaded]
    assert len(set(ids)) == 80
    for pair in loaded:
        prefix = "same" if pair["label"] == "same" else pair["category"]
        assert re.fullmatch(rf"{prefix}-\d{{2}}", pair["id"]), pair["id"]


def test_dataset_pairs_have_exactly_the_five_string_fields() -> None:
    for pair in pairs():
        assert set(pair) == KEYS, pair.get("id")
        assert all(isinstance(value, str) for value in pair.values()), pair["id"]


def test_dataset_texts_are_non_blank_printable_and_differ() -> None:
    for pair in pairs():
        for field in ("first", "second"):
            text = pair[field]
            assert text.strip() == text != "", (pair["id"], field)
            # isprintable rejects control characters and U+2028, which a line scan would miss.
            assert text.isprintable(), (pair["id"], field)
        assert pair["first"] != pair["second"], pair["id"]
