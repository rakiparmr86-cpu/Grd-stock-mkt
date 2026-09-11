from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.config import Watchlist, WatchlistItem
from app.repositories.base import BaseRepository


class WatchlistRepository(BaseRepository[Watchlist]):
    model = Watchlist

    def list_with_items(self) -> list[Watchlist]:
        stmt = select(Watchlist).options(selectinload(Watchlist.items))
        return list(self.db.execute(stmt).scalars())

    def list_active_ids(self) -> list[int]:
        stmt = select(Watchlist.id).where(Watchlist.is_active.is_(True))
        return list(self.db.execute(stmt).scalars())

    def tickers(self, watchlist_id: int) -> list[str]:
        stmt = select(WatchlistItem.ticker).where(WatchlistItem.watchlist_id == watchlist_id)
        return list(self.db.execute(stmt).scalars())

    def add_item(self, watchlist: Watchlist, ticker: str, exchange: str = "NSE",
                weight: float = 1.0) -> WatchlistItem:
        item = WatchlistItem(ticker=ticker.upper(), exchange=exchange, weight=weight)
        watchlist.items.append(item)
        self.db.flush()
        return item
