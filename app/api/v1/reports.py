from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import ReportRepo
from app.models.history import Report
from app.schemas.history import ReportOut

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
