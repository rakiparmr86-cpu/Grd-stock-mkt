"""GET /reports/{id}/excel — builds the same "GRD Calculation" sheet as
scripts/write_grd_calculation.py, straight from a report's own stored
fundamentals_report (no re-upload). Calls the route function directly with a
fake repo rather than a full DB fixture, since Report.payload is Postgres
JSONB (SQLite can't model that column — see tests/test_repositories.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException
from starlette.responses import StreamingResponse

import app.api.v1.reports as reports_module
from app.api.v1.reports import get_report_excel
from app.services.calculations.statistics import full_report


class _FakeReportRepo:
    def __init__(self, report):
        self._report = report

    def get(self, report_id):
        return self._report


def _make_report(payload, ticker="RELIANCE"):
    return SimpleNamespace(id=1, ticker=ticker, payload=payload)


def test_missing_report_404():
    with pytest.raises(HTTPException) as exc:
        get_report_excel(1, _FakeReportRepo(None))
    assert exc.value.status_code == 404


def test_report_without_fundamentals_report_404():
    report = _make_report({"forecast": None})
    with pytest.raises(HTTPException) as exc:
        get_report_excel(1, _FakeReportRepo(report))
    assert exc.value.status_code == 404
    assert "fundamentals" in exc.value.detail


@pytest.fixture
def sample_data_driven():
    years = [str(y) for y in range(2019, 2024)]
    df = pd.DataFrame({
        "revenue": [100.0, 110.0, 121.0, 133.0, 146.0],
        "net_income": [10.0, 12.0, 15.0, 17.0, 20.0],
    }, index=years)
    return full_report(df, target="net_income", features=["revenue"], periods_per_year=1)


def test_report_with_fundamentals_report_returns_xlsx_stream(sample_data_driven):
    report = _make_report({"fundamentals_report": sample_data_driven})

    resp = get_report_excel(1, _FakeReportRepo(report))

    assert isinstance(resp, StreamingResponse)
    assert resp.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'filename="RELIANCE_GRD_Calculation.xlsx"' in resp.headers["content-disposition"]
    assert resp.headers["content-disposition"].startswith("attachment")


def test_writes_sheet_from_the_reports_own_fundamentals_report(monkeypatch, sample_data_driven):
    """The endpoint must hand the report's *own* stored data straight to the
    writer — no scenario/outlook, since a Run has no external growth
    assumptions to build those from."""
    calls = []

    def fake_write(wb, *, scenario_rows=None, outlook_rows=None, data_driven=None,
                   ratio_report=None, sheet_name="GRD Calculation"):
        calls.append({"scenario_rows": scenario_rows, "outlook_rows": outlook_rows,
                      "data_driven": data_driven, "ratio_report": ratio_report})
        return wb.create_sheet(sheet_name)

    monkeypatch.setattr(reports_module, "write_grd_calculation_sheet", fake_write)

    report = _make_report({"fundamentals_report": sample_data_driven})
    get_report_excel(1, _FakeReportRepo(report))

    assert len(calls) == 1
    assert calls[0]["data_driven"] == sample_data_driven
    assert calls[0]["scenario_rows"] is None
    assert calls[0]["outlook_rows"] is None


def test_report_with_only_ratio_report_returns_xlsx_stream():
    """A run can have Margins/Returns/Valuation/Quality ratios computed even
    when there's too little history for the data-driven trend/forecast
    section (< 4 periods) — the endpoint must still serve a workbook rather
    than 404, since there's real content to show."""
    ratio_report = {"margins": {}, "returns": {}, "valuation": {}, "quality": {}}
    report = _make_report({"fundamentals_report": None, "ratio_report": ratio_report})

    resp = get_report_excel(1, _FakeReportRepo(report))

    assert isinstance(resp, StreamingResponse)


def test_writes_ratio_report_to_the_sheet(monkeypatch):
    calls = []

    def fake_write(wb, *, scenario_rows=None, outlook_rows=None, data_driven=None,
                   ratio_report=None, sheet_name="GRD Calculation"):
        calls.append(ratio_report)
        return wb.create_sheet(sheet_name)

    monkeypatch.setattr(reports_module, "write_grd_calculation_sheet", fake_write)

    ratio_report = {"margins": {}, "returns": {}, "valuation": {}, "quality": {}}
    report = _make_report({"ratio_report": ratio_report})
    get_report_excel(1, _FakeReportRepo(report))

    assert calls == [ratio_report]


def test_ticker_falls_back_to_generic_filename_when_missing(sample_data_driven):
    report = _make_report({"fundamentals_report": sample_data_driven}, ticker=None)
    resp = get_report_excel(1, _FakeReportRepo(report))
    assert 'filename="report_GRD_Calculation.xlsx"' in resp.headers["content-disposition"]
