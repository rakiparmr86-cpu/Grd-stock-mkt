from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession, WatchlistRepo
from app.models.config import Watchlist, WatchlistItem
from app.schemas.config import WatchlistCreate, WatchlistOut

router = APIRouter()


@router.get("", response_model=list[WatchlistOut])
def list_watchlists(watchlists: WatchlistRepo) -> list[Watchlist]:
    return watchlists.list_with_items()


@router.post("", response_model=WatchlistOut, status_code=201)
def create_watchlist(payload: WatchlistCreate, db: DbSession,
                     watchlists: WatchlistRepo) -> Watchlist:
    wl = Watchlist(name=payload.name, description=payload.description)
    wl.items = [
        WatchlistItem(ticker=i.ticker.upper(), exchange=i.exchange, weight=i.weight)
        for i in payload.items
    ]
    watchlists.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


@router.get("/{watchlist_id}", response_model=WatchlistOut)
def get_watchlist(watchlist_id: int, watchlists: WatchlistRepo) -> Watchlist:
    wl = watchlists.get(watchlist_id)
    if not wl:
        raise HTTPException(404, "watchlist not found")
    return wl


@router.post("/{watchlist_id}/items", response_model=WatchlistOut)
def add_item(watchlist_id: int, ticker: str, db: DbSession, watchlists: WatchlistRepo,
             exchange: str = "NSE", weight: float = 1.0) -> Watchlist:
    wl = watchlists.get(watchlist_id)
    if not wl:
        raise HTTPException(404, "watchlist not found")
    watchlists.add_item(wl, ticker, exchange, weight)
    db.commit()
    db.refresh(wl)
    return wl


@router.delete("/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: int, db: DbSession, watchlists: WatchlistRepo) -> None:
    wl = watchlists.get(watchlist_id)
    if wl:
        watchlists.delete(wl)
        db.commit()
