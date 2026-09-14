from __future__ import annotations

import io
from pathlib import Path

import openpyxl
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import ReportRepo
from app.models.history import Report
from app.schemas.history import ReportOut
from app.services.reports.excel_writeback import write_grd_calculation_sheet

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter()


@router.get("", response_model=list[ReportOut])
def list_reports(reports: ReportRepo, ticker: str | None = None, run_id: int | None = None,
                 limit: int = 50) -> list[Report]:
    return reports.list_filtered(ticker=ticker, run_id=run_id, limit=limit)


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: int, reports: ReportRepo) -> Report:
    report = reports.get(report_id)
    if not report:
        raise HTTPException(404, "report not found")
    return report


@router.get("/{report_id}/html")
def get_report_html(report_id: int, reports: ReportRepo) -> FileResponse:
    report = reports.get(report_id)
    if not report or not report.html_path or not Path(report.html_path).exists():
        raise HTTPException(404, "rendered HTML not found")
    return FileResponse(report.html_path, media_type="text/html")


@router.get("/{report_id}/excel")
def get_report_excel(report_id: int, reports: ReportRepo) -> StreamingResponse:
    """The same "GRD Calculation" sheet ``scripts/write_grd_calculation.py``
    produces from a manually uploaded statement — built here from the
    fundamental agent's own computed report, no re-upload needed. Only the
    data-driven section is included (scenario Bear/Base/Bull needs external
    growth assumptions a Run doesn't have — see ``/analysis/excel`` for
    that path from an uploaded workbook)."""
    report = reports.get(report_id)
    if not report:
        raise HTTPException(404, "report not found")
    data_driven = (report.payload or {}).get("fundamentals_report")
    if not data_driven:
        raise HTTPException(
            404,
            "no fundamentals data-driven report on this run — needs >= 4 periods of "
            "ingested fundamentals for this ticker (see app/agents/fundamental_analyst.py)",
        )

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_grd_calculation_sheet(wb, data_driven=data_driven)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    ticker = report.ticker or "report"
    filename = f"{ticker}_GRD_Calculation.xlsx"
    return StreamingResponse(
        buf, media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
