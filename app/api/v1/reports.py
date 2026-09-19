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
from app.services.reports.prediction_report import write_prediction_sheets

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
    model = (report.payload or {}).get("prediction_model")
    if model:
        return _prediction_excel(model)
    doc = (report.payload or {}).get("document_analysis")
    if doc:
        return _document_excel(doc, report.title)
    data_driven = (report.payload or {}).get("fundamentals_report")
    ratio_report = (report.payload or {}).get("ratio_report")
    if not data_driven and not ratio_report:
        raise HTTPException(
            404,
            "no fundamentals data-driven report on this run — needs >= 4 periods of "
            "ingested fundamentals for this ticker (see app/agents/fundamental_analyst.py)",
        )

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_grd_calculation_sheet(wb, data_driven=data_driven, ratio_report=ratio_report)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    ticker = report.ticker or "report"
    filename = f"{ticker}_GRD_Calculation.xlsx"
    return StreamingResponse(
        buf, media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _document_excel(doc: dict, title: str) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Document analysis", title])
    for k, v in doc.get("overview", {}).items():
        ws.append([k, v])
    ws.append([])
    ws.append(["Key figure lines"])
    for ln in doc.get("key_lines", []):
        ws.append([ln])
    ws.append([])
    ws.append(["Term", "Count"])
    for k in doc.get("keywords", []):
        ws.append([k["term"], k["count"]])
    cols = ["label", "count", "first", "latest", "min", "max", "mean", "change_pct"]
    for sh in doc.get("sheets", []):
        # Excel sheet names: max 31 chars, no bracket/colon/slash characters
        name = "".join(c for c in sh["name"].split("—")[-1] if c not in "[]:*?/\\").strip()[:31]
        sws = wb.create_sheet(name or f"sheet{len(wb.sheetnames)}")
        sws.append(cols)
        for m in sh["metrics"]:
            sws.append([m.get(c) for c in cols])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=_XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="document_analysis.xlsx"'},
    )


def _prediction_excel(model: dict) -> StreamingResponse:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_prediction_sheets(wb, model)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = "".join(c if c.isalnum() else "_" for c in model["company"]).strip("_")
    return StreamingResponse(
        buf, media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{name}_Prediction.xlsx"'},
    )
