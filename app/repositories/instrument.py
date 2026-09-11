from __future__ import annotations

from sqlalchemy import select

from app.models.market import Instrument
from app.repositories.base import BaseRepository


class InstrumentRepository(BaseRepository[Instrument]):
    model = Instrument

    def all_tickers(self) -> set[str]:
        return {t for (t,) in self.db.execute(select(Instrument.ticker)).all()}
