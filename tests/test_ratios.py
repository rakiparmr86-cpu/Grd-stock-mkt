from __future__ import annotations

import pandas as pd
import pytest

from app.services.calculations.ratios import full_ratio_report, margins, quality, returns, valuation


@pytest.fixture
def statement_df():
    """A synthetic 3-year statement with both P&L and Balance Sheet line
    items, shaped the way ``load_fundamentals_frame_full`` would hand it to
    the ratio engine (typed columns + lowercased free-form metrics)."""
    years = ["2021", "2022", "2023"]
    return pd.DataFrame({
        "revenue": [1000.0, 1100.0, 1250.0],
        "net_income": [100.0, 120.0, 150.0],
        "operating profit": [180.0, 200.0, 230.0],
        "depreciation": [20.0, 22.0, 25.0],
        "equity share capital": [50.0, 50.0, 50.0],
        "reserves": [450.0, 550.0, 680.0],
        "total assets": [1200.0, 1350.0, 1500.0],
        "borrowings": [300.0, 280.0, 260.0],
        "cash from operating activity": [90.0, 110.0, 140.0],
        "eps": [10.0, 12.0, 15.0],
        "shares outstanding": [10.0, 10.0, 10.0],
    }, index=years)


def test_margins_computes_opm_and_net_margin(statement_df):
    result = margins(statement_df)
    opm = result["operating_profit_margin_pct"]
    assert opm["insufficient_data"] is False
    assert opm["latest"] == pytest.approx(230.0 / 1250.0 * 100)

    net_margin = result["net_profit_margin_pct"]
    assert net_margin["latest"] == pytest.approx(150.0 / 1250.0 * 100)


def test_margins_nim_insufficient_without_bank_fields(statement_df):
    result = margins(statement_df)
    nim = result["net_interest_margin_pct"]
    assert nim["insufficient_data"] is True
    assert "interest earned" in nim["reason"]


def test_returns_roe_roa_roce(statement_df):
    result = returns(statement_df)
    # equity = equity share capital + reserves = 50 + 680 = 730 (latest)
    assert result["roe_pct"]["latest"] == pytest.approx(150.0 / 730.0 * 100)
    assert result["roa_pct"]["latest"] == pytest.approx(150.0 / 1500.0 * 100)
    # capital employed = equity + borrowings = 730 + 260 = 990
    assert result["roce_pct"]["latest"] == pytest.approx(230.0 / 990.0 * 100)
    assert "approximated" in result["roce_pct"]["note"]


def test_valuation_uses_supplied_price_for_pe_pb_ev(statement_df):
    result = valuation(statement_df, price=180.0)
    # no 'pe' column in the fixture -> falls back to price / eps
    assert result["pe"]["insufficient_data"] is False
    assert result["pe"]["latest"] == pytest.approx(180.0 / 15.0)

    # book value per share = equity / shares = 730 / 10 = 73
    assert result["pb"]["latest"] == pytest.approx(180.0 / 73.0)

    # EV = market cap + borrowings = 1800 + 260 = 2060; EBITDA = 230 + 25 = 255
    assert result["ev_to_ebitda"]["latest"] == pytest.approx(2060.0 / 255.0)
    assert result["ev_to_sales"]["latest"] == pytest.approx(2060.0 / 1250.0)


def test_valuation_without_price_is_insufficient_for_pb_and_ev(statement_df):
    result = valuation(statement_df, price=None)
    assert result["pe"]["insufficient_data"] is True
    assert result["pb"]["insufficient_data"] is True
    assert result["ev_to_ebitda"]["insufficient_data"] is True


def test_quality_cash_conversion_and_leverage(statement_df):
    result = quality(statement_df)
    assert result["cash_conversion"]["latest"] == pytest.approx(140.0 / 150.0)
    assert result["leverage_debt_to_equity"]["latest"] == pytest.approx(260.0 / 730.0)
    # no NPA field -> falls back to asset turnover proxy
    asset_quality = result["asset_quality"]
    assert asset_quality["metric"] == "asset_turnover_pct"
    assert asset_quality["latest"] == pytest.approx(1250.0 / 1500.0 * 100)


def test_full_ratio_report_groups_all_four_categories(statement_df):
    report = full_ratio_report(statement_df, price=180.0)
    assert set(report) == {"margins", "returns", "valuation", "quality"}


def test_ratio_missing_everything_degrades_gracefully():
    df = pd.DataFrame({"unrelated_col": [1, 2, 3]}, index=["2021", "2022", "2023"])
    report = full_ratio_report(df)
    assert report["margins"]["operating_profit_margin_pct"]["insufficient_data"] is True
    assert report["returns"]["roe_pct"]["insufficient_data"] is True
    assert report["valuation"]["pe"]["insufficient_data"] is True
    assert report["quality"]["cash_conversion"]["insufficient_data"] is True
