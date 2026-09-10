from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.services.notifications.base import Notification, NotificationChannel

log = get_logger(__name__)


class EmailChannel(NotificationChannel):
    name = "email"

    def send(self, msg: Notification) -> dict:
        email = EmailMessage()
        email["From"] = settings.smtp_from
        email["To"] = msg.recipient
        email["Subject"] = msg.subject
        email.set_content(msg.body_text)
        if msg.body_html:
            email.add_alternative(msg.body_html, subtype="html")

        for path_str in msg.attachments:
            p = Path(path_str)
            if not p.exists():
                log.warning("attachment missing, skipped: %s", p)
                continue
            email.add_attachment(
                p.read_bytes(),
                maintype="application",
                subtype="octet-stream",
                filename=p.name,
            )

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as srv:
                if settings.smtp_tls:
                    srv.starttls(context=ssl.create_default_context())
                if settings.smtp_user:
                    srv.login(settings.smtp_user, settings.smtp_password)
                srv.send_message(email)
            log.info("email sent to %s (%s)", msg.recipient, msg.subject)
            return {"status": "sent", "channel": self.name}
        except Exception as exc:  # noqa: BLE001 - channels must not raise
            log.exception("email send failed")
            return {"status": "failed", "channel": self.name, "error": str(exc)}
