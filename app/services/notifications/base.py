from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class Notification:
    recipient: str
    subject: str
    body_text: str
    body_html: str | None = None
    attachments: list[str] = field(default_factory=list)  # file paths
    meta: dict = field(default_factory=dict)


class NotificationChannel(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def send(self, msg: Notification) -> dict:
        """Return {'status': 'sent'|'failed', ...}. Must not raise."""
