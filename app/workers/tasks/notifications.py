"""Notification dispatch tasks."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.history import Alert
from app.repositories.alert import AlertRepository
from app.services.notifications import notify
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.notifications.send_report_alert")
def send_report_alert(run_id: int, ticker: str, recipient: str, report: dict,
                      channel: str | None = None) -> dict:
    rec = (report or {}).get("recommendation", {})
    action = rec.get("action", "REVIEW")
    subject = f"[grd-stk-mkt] {ticker}: {action}"
    body_text = (
        f"{ticker} — {action}\n\n"
        f"{rec.get('thesis', '')}\n\n"
        f"Run #{run_id}. Full report attached / see dashboard."
    )
    attachments = [p for p in [report.get("html_path"), report.get("pdf_path")] if p]

    with session_scope() as db:
        alert = AlertRepository(db).add(
            Alert(channel=channel or "email", recipient=recipient, status="queued")
        )
        alert_id = alert.id

    result = notify(recipient, subject, body_text,
                    body_html=report.get("html"), attachments=attachments,
                    channel=channel)

    with session_scope() as db:
        alerts = AlertRepository(db)
        alert = alerts.get(alert_id)
        if alert:
            alert.status = "sent" if result.get("status") == "sent" else "failed"
            alert.error = result.get("error")
            alert.sent_at = datetime.now(timezone.utc)
    return {"alert_id": alert_id, **result}
