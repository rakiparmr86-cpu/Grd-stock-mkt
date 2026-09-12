from __future__ import annotations

import openpyxl
import pandas as pd
import pytest

from app.services.calculations.scenario import multi_year_outlook, scenario_projection
from app.services.calculations.statistics import full_report
from app.services.reports.excel_writeback import write_grd_calculation_sheet


@pytest.fixture
def scenario_and_outlook():
    scenario_rows = scenario_projection(
        ttm_sales=100.0, ttm_net_profit=10.0, shares_outstanding=5.0, current_price=20.0,
        sales_growth={"bear": 0.01, "base": 0.05, "bull": 0.08},
        profit_growth={"bear": 0.03, "base": 0.09, "bull": 0.14},
        target_pe={"bear": 12.5, "base": 15, "bull": 17},
    )
    outlook_rows = multi_year_outlook(100.0, 10.0, 5.0, 0.05, 0.09, years=3)
    return scenario_rows, outlook_rows


def test_write_sheet_creates_expected_structure(tmp_path, scenario_and_outlook):
    scenario_rows, outlook_rows = scenario_and_outlook
    wb = openpyxl.Workbook()
    write_grd_calculation_sheet(wb, scenario_rows=scenario_rows, outlook_rows=outlook_rows)

    assert "GRD Calculation" in wb.sheetnames
    ws = wb["GRD Calculation"]
    values = [[c.value for c in row] for row in ws.iter_rows()]
    flat_col1 = [row[0] for row in values]
    assert "GRD CALCULATION" in flat_col1
    assert "1. SCENARIO PROJECTION (next period)" in flat_col1
    assert "2. MULTI-YEAR OUTLOOK (base case, compounded)" in flat_col1
    assert "Sales" in flat_col1

    out_path = tmp_path / "out.xlsx"
    wb.save(out_path)
    reloaded = openpyxl.load_workbook(out_path)
    assert "GRD Calculation" in reloaded.sheetnames


def test_write_sheet_replaces_existing_sheet_of_same_name(scenario_and_outlook):
    scenario_rows, outlook_rows = scenario_and_outlook
    wb = openpyxl.Workbook()
    write_grd_calculation_sheet(wb, scenario_rows=scenario_rows, outlook_rows=outlook_rows)
    first_count = len(wb.sheetnames)
    write_grd_calculation_sheet(wb, scenario_rows=scenario_rows, outlook_rows=outlook_rows)
    assert len(wb.sheetnames) == first_count  # replaced, not duplicated


def test_write_sheet_preserves_other_sheets(scenario_and_outlook):
    scenario_rows, outlook_rows = scenario_and_outlook
    wb = openpyxl.Workbook()
    wb.active.title = "Profit & Loss"
    wb["Profit & Loss"]["A1"] = "keep me"
    write_grd_calculation_sheet(wb, scenario_rows=scenario_rows, outlook_rows=outlook_rows)
    assert wb["Profit & Loss"]["A1"].value == "keep me"
    assert "GRD Calculation" in wb.sheetnames


def test_write_sheet_includes_data_driven_section():
    years = [str(y) for y in range(2019, 2024)]
    df = pd.DataFrame({
        "sales": [100.0, 110.0, 121.0, 133.0, 146.0],
        "net_profit": [10.0, 12.0, 15.0, 17.0, 20.0],
    }, index=years)
    report = full_report(df, target="net_profit", features=["sales"], periods_per_year=1)

    wb = openpyxl.Workbook()
    write_grd_calculation_sheet(wb, data_driven=report)
    ws = wb["GRD Calculation"]
    flat_col1 = [c.value for row in ws.iter_rows() for c in [row[0]]]
    assert any("DATA-DRIVEN CROSS-CHECK" in str(v) for v in flat_col1 if v)
    assert "sales" in flat_col1
    assert "net_profit" in flat_col1
