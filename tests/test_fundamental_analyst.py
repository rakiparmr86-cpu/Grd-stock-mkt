"""Fundamental analyst: single-period valuation score (existing behavior) plus
a data-driven trend/forecast cross-check over the ticker's full Fundamental
history — DB access is monkeypatched so these stay fast, offline unit tests."""

from __future__ import annotations

import pandas as pd
import pytest

from app.agents.fundamental_analyst import fundamental_analyst_node
from app.agents.report_writer import report_writer_node


class _FakeFundamental:
    def __init__(self, **kw):
        self.period = kw.get("period", "FY2024")
        self.pe = kw.get("pe")
        self.eps = kw.get("eps")
        self.revenue = kw.get("revenue")
        self.net_income = kw.get("net_income")
        self.debt_to_equity = kw.get("debt_to_equity")
        self.metrics = kw.get("metrics", {})


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")


def test_no_fundamentals_on_file(monkeypatch):
    monkeypatch.setattr(
        "app.agents.fundamental_analyst._latest_fundamental", lambda ticker: None
    )
    state = {"ticker": "NOPE", "findings": [], "decisions": []}
    out = fundamental_analyst_node(state)
    finding = out["findings"][0]
    assert finding["stance"] == "no_data"
    assert "forecast" not in finding or finding.get("forecast") is None


def test_single_period_no_forecast_section(monkeypatch):
    monkeypatch.setattr(
        "app.agents.fundamental_analyst._latest_fundamental",
        lambda ticker: _FakeFundamental(pe=12.0, revenue=100.0, net_income=15.0),
    )
    monkeypatch.setattr(
        "app.agents.fundamental_analyst.load_fundamentals_frame",
        lambda ticker: pd.DataFrame({"revenue": [100.0], "net_income": [15.0]}, index=["FY2024"]),
    )
    state = {"ticker": "ONEROW", "findings": [], "decisions": []}
    out = fundamental_analyst_node(state)
    finding = out["findings"][0]
    assert finding["stance"] in {"cheap", "fair", "expensive"}
    assert finding["forecast"] is None
    assert not any("CAGR" in b for b in finding["bullets"])


def test_enough_history_adds_forecast(monkeypatch):
    monkeypatch.setattr(
        "app.agents.fundamental_analyst._latest_fundamental",
        lambda ticker: _FakeFundamental(pe=12.0, revenue=146.0, net_income=20.0),
    )
    years = [str(y) for y in range(2019, 2024)]
    frame = pd.DataFrame({
        "revenue": [100.0, 110.0, 121.0, 133.0, 146.0],
        "net_income": [10.0, 12.0, 15.0, 17.0, 20.0],
    }, index=years)
    monkeypatch.setattr(
        "app.agents.fundamental_analyst.load_fundamentals_frame", lambda ticker: frame
    )
    state = {"ticker": "GROWCO", "findings": [], "decisions": []}
    out = fundamental_analyst_node(state)
    finding = out["findings"][0]

    assert finding["forecast"] is not None
    assert set(finding["forecast"]) == {"revenue", "net_income"}
    rev = finding["forecast"]["revenue"]
    assert rev["cagr_pct"] > 0
    assert rev["trend_direction"] == "up"

    # the full calculation-engine report (for Excel export) must be the same
    # shape app.services.reports.excel_writeback expects — not just the
    # flattened "forecast" summary used for on-screen bullets
    report = finding["fundamentals_report"]
    assert report is not None
    assert set(report["metrics"]) == {"revenue", "net_income"}
    assert "descriptive_stats" in report["metrics"]["revenue"]
    assert "growth_trend" in report["metrics"]["revenue"]
    assert report["regression"]["target"] == "net_income"
    assert report["regression"]["features"] == ["revenue"]
    ci = rev["confidence_interval_95"]
    assert ci["low"] <= rev["forecast_next"] <= ci["high"]
    assert any("revenue" in b and "CAGR" in b for b in finding["bullets"])


def test_forecast_skips_metric_with_insufficient_history(monkeypatch):
    monkeypatch.setattr(
        "app.agents.fundamental_analyst._latest_fundamental",
        lambda ticker: _FakeFundamental(revenue=146.0, net_income=20.0),
    )
    # revenue has 4 periods (enough), net_income only has 2 non-null values
    frame = pd.DataFrame({
        "revenue": [100.0, 110.0, 121.0, 133.0],
        "net_income": [None, None, 17.0, 20.0],
    }, index=[str(y) for y in range(2020, 2024)])
    monkeypatch.setattr(
        "app.agents.fundamental_analyst.load_fundamentals_frame", lambda ticker: frame
    )
    state = {"ticker": "PARTIAL", "findings": [], "decisions": []}
    out = fundamental_analyst_node(state)
    finding = out["findings"][0]
    assert finding["forecast"] is not None
    assert set(finding["forecast"]) == {"revenue"}


def test_report_writer_includes_forecast_when_present():
    state = {
        "ticker": "GROWCO",
        "risk_review": {"verdict": "go", "conviction": 0.5},
        "findings": [{
            "agent": "fundamental_analyst",
            "forecast": {"revenue": {"cagr_pct": 10.0, "trend_direction": "up",
                                     "forecast_next": 160.0,
                                     "confidence_interval_95": {"low": 150.0, "high": 170.0}}},
            "narrative": "", "bullets": [],
        }],
        "signals": [], "decisions": [],
    }
    out = report_writer_node(state)
    assert out["report_payload"]["forecast"] == state["findings"][0]["forecast"]


def test_report_writer_forecast_none_when_absent():
    state = {
        "ticker": "NOPE",
        "risk_review": {"verdict": "no-go", "conviction": -0.3},
        "findings": [{"agent": "fundamental_analyst", "forecast": None,
                      "narrative": "", "bullets": []}],
        "signals": [], "decisions": [],
    }
    out = report_writer_node(state)
    assert out["report_payload"]["forecast"] is None
