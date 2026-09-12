from __future__ import annotations

import pytest

from app.services.calculations.scenario import multi_year_outlook, scenario_projection

# Real figures from the user's own GRDPrediction_Model.xlsx "Prediction
# Inputs" / "Prediction Report" sheets (HDFC Bank) — used here to prove our
# implementation reproduces that sheet's numbers exactly, not just plausible
# ones.
TTM_SALES = 351818.61
TTM_NET_PROFIT = 79012.76999999999
TTM_EPS = 51.27457397295704
SHARES = TTM_NET_PROFIT / TTM_EPS
CURRENT_PRICE = 708

SALES_GROWTH = {"bear": 0.01, "base": 0.05, "bull": 0.08}
PROFIT_GROWTH = {"bear": 0.03, "base": 0.09, "bull": 0.14}
TARGET_PE = {"bear": 12.5, "base": 15, "bull": 17}


def test_scenario_projection_matches_workbook_bear_case():
    out = scenario_projection(
        TTM_SALES, TTM_NET_PROFIT, SHARES, CURRENT_PRICE, SALES_GROWTH, PROFIT_GROWTH, TARGET_PE
    )
    bear = out["bear"]
    assert bear["sales"] == pytest.approx(355336.7961, abs=1e-4)
    assert bear["net_profit"] == pytest.approx(81383.1531, abs=1e-4)
    assert bear["eps"] == pytest.approx(52.81281119214576, rel=1e-9)
    assert bear["implied_price"] == pytest.approx(660.1601399018219, rel=1e-9)
    assert bear["upside_downside_pct"] == pytest.approx(-6.757042386748313, rel=1e-9)


def test_scenario_projection_matches_workbook_base_case():
    out = scenario_projection(
        TTM_SALES, TTM_NET_PROFIT, SHARES, CURRENT_PRICE, SALES_GROWTH, PROFIT_GROWTH, TARGET_PE
    )
    base = out["base"]
    assert base["sales"] == pytest.approx(369409.5405, abs=1e-4)
    assert base["net_profit"] == pytest.approx(86123.9193, abs=1e-4)
    assert base["implied_price"] == pytest.approx(838.3392844578477, rel=1e-9)
    assert base["upside_downside_pct"] == pytest.approx(18.409503454498277, rel=1e-9)


def test_scenario_projection_matches_workbook_bull_case():
    out = scenario_projection(
        TTM_SALES, TTM_NET_PROFIT, SHARES, CURRENT_PRICE, SALES_GROWTH, PROFIT_GROWTH, TARGET_PE
    )
    bull = out["bull"]
    assert bull["sales"] == pytest.approx(379964.0988, abs=1e-4)
    assert bull["net_profit"] == pytest.approx(90074.5578, abs=1e-4)
    assert bull["implied_price"] == pytest.approx(993.7012435959076, rel=1e-9)
    assert bull["upside_downside_pct"] == pytest.approx(40.353282993772255, rel=1e-9)


def test_scenario_projection_rejects_mismatched_keys():
    with pytest.raises(ValueError, match="same scenario keys"):
        scenario_projection(
            TTM_SALES, TTM_NET_PROFIT, SHARES, CURRENT_PRICE,
            {"bear": 0.01}, {"base": 0.09}, {"bear": 12.5},
        )


def test_scenario_projection_rejects_zero_shares():
    with pytest.raises(ValueError, match="shares_outstanding"):
        scenario_projection(
            TTM_SALES, TTM_NET_PROFIT, 0, CURRENT_PRICE, SALES_GROWTH, PROFIT_GROWTH, TARGET_PE
        )


def test_multi_year_outlook_matches_workbook_base_case():
    rows = multi_year_outlook(
        TTM_SALES, TTM_NET_PROFIT, SHARES,
        sales_growth=SALES_GROWTH["base"], profit_growth=PROFIT_GROWTH["base"],
        years=3, start_label="FY26 / TTM",
        year_label_fn=lambda i: f"FY{26 + i}E",
    )
    by_period = {r["period"]: r for r in rows}
    assert by_period["FY26 / TTM"]["sales"] == pytest.approx(TTM_SALES)
    assert by_period["FY27E"]["sales"] == pytest.approx(369409.5405, abs=1e-4)
    assert by_period["FY27E"]["net_profit"] == pytest.approx(86123.9193, abs=1e-4)
    assert by_period["FY27E"]["eps"] == pytest.approx(55.88928563052318, rel=1e-9)
    assert by_period["FY28E"]["sales"] == pytest.approx(387880.01752500003, abs=1e-4)
    assert by_period["FY28E"]["net_profit"] == pytest.approx(93875.072037, abs=1e-4)
    assert by_period["FY28E"]["eps"] == pytest.approx(60.919321337270276, rel=1e-9)
    assert by_period["FY29E"]["sales"] == pytest.approx(407274.01840125007, abs=1e-4)
    assert by_period["FY29E"]["net_profit"] == pytest.approx(102323.82852033002, abs=1e-4)
    assert by_period["FY29E"]["eps"] == pytest.approx(66.40206025762461, rel=1e-9)


def test_multi_year_outlook_length():
    rows = multi_year_outlook(100.0, 10.0, 5.0, 0.05, 0.09, years=3)
    assert len(rows) == 4  # start + 3 projected years
