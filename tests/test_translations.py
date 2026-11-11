"""Tests that keep the translation files in sync."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

COMPONENT_DIR = (
    Path(__file__).parents[1] / "custom_components" / "yealink_t54w"
)


def _load(name: str) -> dict[str, Any]:
    return json.loads((COMPONENT_DIR / name).read_text(encoding="utf-8"))


def _flatten(data: Any, prefix: str = "") -> Iterator[str]:
    if isinstance(data, dict):
        for key, value in data.items():
            child = f"{prefix}.{key}" if prefix else key
            yield from _flatten(value, child)
        return
    yield prefix


def test_translation_files_are_valid_json() -> None:
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        assert _load(name)


def test_german_translation_covers_every_english_key() -> None:
    english = set(_flatten(_load("strings.json")))
    german = set(_flatten(_load("translations/de.json")))

    assert english - german == set()


def test_english_translation_matches_strings_json() -> None:
    assert _load("strings.json") == _load("translations/en.json")
