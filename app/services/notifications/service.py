"""Channel registry + dispatch. WhatsApp / Telegram slot in here later."""

from __future__ import annotations

from app.core.config import settings
from app.services.notifications.base import Notification, NotificationChannel
from app.services.notifications.email import EmailChannel

_CHANNELS: dict[str, NotificationChannel] = {
    "email": EmailChannel(),
    # "whatsapp": WhatsAppChannel(),   # TODO
    # "telegram": TelegramChannel(),   # TODO
}


class NotificationService:
    def __init__(self, channels: dict[str, NotificationChannel] | None = None) -> None:
        self.channels = channels or _CHANNELS

    def send(self, msg: Notification, channel: str | None = None) -> dict:
        name = channel or settings.notify_default_channel
        ch = self.channels.get(name)
        if ch is None:
            return {"status": "failed", "error": f"unknown channel {name!r}"}
        return ch.send(msg)


def notify(
    recipient: str,
    subject: str,
    body_text: str,
    *,
    body_html: str | None = None,
    attachments: list[str] | None = None,
    channel: str | None = None,
) -> dict:
    msg = Notification(
        recipient=recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments or [],
    )
    return NotificationService().send(msg, channel=channel)
