"""Unit tests for :mod:`backend.app.metrics` histogram helpers."""

from __future__ import annotations

import pytest

from backend.app.metrics import Histogram


def test_percentiles_even_number_of_samples() -> None:
    histogram = Histogram()
    histogram.add(10)
    histogram.add(20)

    snapshot = histogram.percentiles()

    assert snapshot["p50"] == pytest.approx(15.0)
    assert snapshot["p95"] == pytest.approx(19.5)


def test_percentiles_single_sample() -> None:
    histogram = Histogram()
    histogram.add(7)

    snapshot = histogram.percentiles()

    assert snapshot["p50"] == pytest.approx(7.0)
    assert snapshot["p95"] == pytest.approx(7.0)


def test_percentiles_empty_histogram() -> None:
    histogram = Histogram()

    assert histogram.percentiles() == {"p50": 0.0, "p95": 0.0}
