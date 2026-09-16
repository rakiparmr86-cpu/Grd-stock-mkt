"""_json_safe: NaN/Infinity have no JSON representation, so a single such
value anywhere in a Fundamental row's ``metrics`` blob fails the *entire*
batch insert into the JSONB column (Postgres rejects the whole statement,
not just that key) — a real bug hit live when a Screener Balance Sheet
export's Return on Capital Employed divided by zero in early years."""

from __future__ import annotations

from app.services.market_data.repository import _json_safe


def test_nan_becomes_none():
    assert _json_safe(float("nan")) is None


def test_positive_and_negative_infinity_become_none():
    assert _json_safe(float("inf")) is None
    assert _json_safe(float("-inf")) is None


def test_ordinary_float_passes_through():
    assert _json_safe(123.45) == 123.45


def test_ordinary_zero_passes_through():
    # zero is a legitimate value (e.g. a metric that's genuinely 0) and must
    # not be conflated with the None-ing of NaN/Infinity
    assert _json_safe(0.0) == 0.0


def test_non_float_values_pass_through_unchanged():
    assert _json_safe("cheap") == "cheap"
    assert _json_safe(None) is None
    assert _json_safe(42) == 42
