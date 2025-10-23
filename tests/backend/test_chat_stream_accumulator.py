"""Tests for the chat streaming accumulator logic."""

from __future__ import annotations

from typing import Mapping

import pytest

from backend.app.api.chat import _StreamAccumulator


def _chunk_with_content(text: str) -> Mapping[str, object]:
    return {"message": {"content": text}}


def test_accumulator_handles_cumulative_content() -> None:
    accumulator = _StreamAccumulator()

    first = accumulator.update(_chunk_with_content("Hello"))
    assert first is not None
    assert first.delta == "Hello"
    assert first.answer == "Hello"

    second = accumulator.update(_chunk_with_content("Hello, world"))
    assert second is not None
    assert second.delta == ", world"
    assert second.answer == "Hello, world"


def test_accumulator_appends_incremental_tokens() -> None:
    accumulator = _StreamAccumulator()

    for token in ("H", "e", "l", "l", "o"):
        delta = accumulator.update(_chunk_with_content(token))
        assert delta is not None

    assert accumulator.answer == "Hello"


@pytest.mark.parametrize(
    "sequence, expected",
    [
        (("H", "He", "Hel", "Hell", "Hello"), "Hello"),
        (("A", "B", "C"), "ABC"),
    ],
)
def test_accumulator_retains_full_answer(sequence: tuple[str, ...], expected: str) -> None:
    accumulator = _StreamAccumulator()

    for chunk in sequence:
        accumulator.update(_chunk_with_content(chunk))

    assert accumulator.answer == expected
