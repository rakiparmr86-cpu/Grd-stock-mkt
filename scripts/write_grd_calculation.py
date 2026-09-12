"""Compute a "GRD Calculation" sheet — a scenario projection + multi-year
outlook (from the workbook's own "Prediction Inputs" sheet) plus a
data-driven cross-check (historical trend + ETS forecast) from the
calculation engine — and write it to its own standalone workbook.

    python scripts/write_grd_calculation.py SOURCE.xlsx
    python scripts/write_grd_calculation.py SOURCE.xlsx --output OUT.xlsx \
        --statement-sheet "Profit & Loss" --inputs-sheet "Prediction Inputs" \
        --target "Net profit" --features Sales

Deliberately does NOT modify SOURCE.xlsx or save the new sheet into a copy of
it: openpyxl only keeps a formula cell's *formula*, not its last-calculated
value, when a workbook is loaded normally (not ``data_only=True``) — saving
such a workbook back out drops every formula cell's cached display value
(the formulas themselves are untouched, so Excel recalculates them correctly
the next time a person opens the file, but any tool reading the file's raw
values in between, ours included, would see blanks until then). Writing a
fresh single-sheet workbook sidesteps that entirely. Use Excel's own
"Move or Copy Sheet" to merge it into SOURCE.xlsx by hand — that goes through
Excel's own formula engine, not openpyxl's serializer, so it has none of
this caveat.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from app.services.calculations.scenario import multi_year_outlook, scenario_projection
from app.services.calculations.statistics import full_report
from app.services.inputs.screener_excel import load_prediction_inputs, transpose_statement_sheet
from app.services.reports.excel_writeback import write_grd_calculation_sheet


def _outlook_labels(last_period: str) -> tuple[str, callable]:
    """Best-effort "FY26 / TTM", "FY27E", ... labels from a "YYYY-MM" period
    like the statement sheet's last historical column; falls back to the
    writeback module's generic "TTM" / "Year +N" labels if it doesn't match.
    """
    m = re.match(r"^(\d{4})-\d{2}$", last_period)
    if not m:
        return "TTM", (lambda i: f"Year +{i}")
    fy = int(m.group(1)) % 100
    return f"FY{fy} / TTM", (lambda i: f"FY{fy + i}E")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("source", help="path to the source .xlsx workbook (read-only, never modified)")
    ap.add_argument("--output", default=None,
                    help="output path (default: SOURCE with '.GRD_Calculation' before the "
                         "extension)")
    ap.add_argument("--statement-sheet", default="Profit & Loss",
                    help="row-per-metric statement sheet to source historical data from")
    ap.add_argument("--inputs-sheet", default="Prediction Inputs",
                    help="sheet with TTM actuals + Bear/Base/Bull scenario assumptions")
    ap.add_argument("--target", default="Net profit",
                    help="metric to regress/forecast as the target")
    ap.add_argument("--features", nargs="*", default=["Sales"],
                    help="metric(s) to regress target on")
    ap.add_argument("--outlook-years", type=int, default=3)
    args = ap.parse_args(argv)

    path = Path(args.source)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1
    output_path = Path(args.output) if args.output else path.with_name(
        f"{path.stem}.GRD_Calculation.xlsx"
    )

    raw_statement = pd.read_excel(path, sheet_name=args.statement_sheet, header=None)
    df = transpose_statement_sheet(raw_statement)

    raw_inputs = pd.read_excel(path, sheet_name=args.inputs_sheet, header=None)
    inputs = load_prediction_inputs(raw_inputs)

    scenario_rows = scenario_projection(
        ttm_sales=inputs["ttm_sales"],
        ttm_net_profit=inputs["ttm_net_profit"],
        shares_outstanding=inputs["shares_outstanding"],
        current_price=inputs["current_price"],
        sales_growth=inputs["sales_growth"],
        profit_growth=inputs["profit_growth"],
        target_pe=inputs["target_pe"],
    )
    start_label, year_label_fn = _outlook_labels(str(df.index[-1]))
    outlook_rows = multi_year_outlook(
        ttm_sales=inputs["ttm_sales"],
        ttm_net_profit=inputs["ttm_net_profit"],
        shares_outstanding=inputs["shares_outstanding"],
        sales_growth=inputs["sales_growth"]["base"],
        profit_growth=inputs["profit_growth"]["base"],
        years=args.outlook_years,
        start_label=start_label,
        year_label_fn=year_label_fn,
    )

    missing = [c for c in (args.target, *args.features) if c not in df.columns]
    if missing:
        print(
            f"warning: {missing} not found in {args.statement_sheet!r} — "
            "skipping data-driven section",
            file=sys.stderr,
        )
        data_driven = None
    else:
        data_driven = full_report(
            df[[args.target, *args.features]], target=args.target, features=args.features,
            periods_per_year=1, forecast_periods=1,
        )

    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # drop the default blank sheet — we only want ours
    write_grd_calculation_sheet(wb, scenario_rows=scenario_rows, outlook_rows=outlook_rows,
                                data_driven=data_driven)
    wb.save(output_path)
    print(f"wrote standalone 'GRD Calculation' sheet to {output_path}")
    print(f"'{path.name}' was not modified — use Excel's Move/Copy Sheet to merge it in by hand")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
