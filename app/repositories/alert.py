from __future__ import annotations

from app.models.history import Alert
from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    model = Alert
