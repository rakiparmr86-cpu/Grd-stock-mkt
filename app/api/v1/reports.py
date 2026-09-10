from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.history import Report
from app.schemas.history import ReportOut

router = APIRouter()


@router.get("", response_model=list[ReportOut])
def list_reports(db: DbSession, ticker: str | None = None, run_id: int | None = None,
                 limit: int = 50) -> list[Report]:
    q = select(Report).order_by(Report.id.desc()).limit(limit)
    if ticker:
        q = q.where(Report.ticker == ticker.upper())
    if run_id is not None:
        q = q.where(Report.run_id == run_id)
    return list(db.execute(q).scalars())


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: DbSession) -> Report:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "report not found")
    return report


@router.get("/{report_id}/html")
def get_report_html(report_id: int, db: DbSession) -> FileResponse:
    report = db.get(Report, report_id)
    if not report or not report.html_path or not Path(report.html_path).exists():
        raise HTTPException(404, "rendered HTML not found")
    return FileResponse(report.html_path, media_type="text/html")
