"""The HTML report must actually show the 5-year forecast path, not just the
narrative bullets — a real gap found live: fundamentals_report/ratio_report
reach the Excel export, but the renderer's template only ever read
recommendation/chart/signals/sections/indicators from the payload, silently
dropping the forecast entirely."""

from __future__ import annotations

from app.services.reports.renderer import ReportRenderer


def _payload(forecast=None):
    return {
        "title": "TESTCO — analysis report",
        "run_id": 1,
        "recommendation": {"action": "BUY", "confidence": 0.6, "thesis": "looks fine"},
        "sections": [],
        "indicators": {},
        "forecast": forecast,
    }


def test_render_html_includes_forecast_table_when_present():
    forecast = {
        "revenue": {
            "cagr_pct": 8.2, "trend_direction": "up",
            "forecast_path": [
                {"year": 1, "period": "FY25E", "value": 160.0, "ci_low": 150.0,
                 "ci_high": 170.0, "yoy_pct": 9.6},
                {"year": 2, "period": "FY26E", "value": 173.0, "ci_low": 155.0,
                 "ci_high": 191.0, "yoy_pct": 8.1},
            ],
        },
    }
    html = ReportRenderer().render_html(_payload(forecast))
    assert "5-year forecast" in html
    assert "Revenue" in html
    assert "FY25E" in html and "FY26E" in html
    assert "9.6" in html


def test_render_html_omits_forecast_section_when_absent():
    html = ReportRenderer().render_html(_payload(None))
    assert "5-year forecast" not in html
