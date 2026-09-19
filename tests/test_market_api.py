"""GET /market/tickers and /market/ohlcv/{ticker} — price bars for the charts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.market import get_ohlcv, list_price_tickers


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return iter(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return _Result(self._rows)


def _bar(i):
    return SimpleNamespace(
        ts=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=10 + i, high=12 + i, low=9 + i, close=11 + i, volume=1000,
    )


def test_ohlcv_returns_oldest_first():
    newest_first = [_bar(2), _bar(1), _bar(0)]  # what ORDER BY ts DESC yields
    out = get_ohlcv("infy", _FakeDb(newest_first), limit=5)
    assert out["ticker"] == "INFY"
    closes = [b["close"] for b in out["bars"]]
    assert closes == [11.0, 12.0, 13.0]


def test_ohlcv_404_when_no_data():
    with pytest.raises(HTTPException) as e:
        get_ohlcv("nope", _FakeDb([]), limit=5)
    assert e.value.status_code == 404


def test_tickers_listing():
    last = datetime(2026, 1, 9, tzinfo=UTC)
    out = list_price_tickers(_FakeDb([("INFY", 500, last)]))
    assert out == [{"ticker": "INFY", "bars": 500, "last": last.isoformat()}]
