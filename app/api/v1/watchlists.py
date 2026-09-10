from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.models.config import Watchlist, WatchlistItem
from app.schemas.config import WatchlistCreate, WatchlistOut

router = APIRouter()


@router.get("", response_model=list[WatchlistOut])
def list_watchlists(db: DbSession) -> list[Watchlist]:
    return list(
        db.execute(select(Watchlist).options(selectinload(Watchlist.items))).scalars()
    )


@router.post("", response_model=WatchlistOut, status_code=201)
def create_watchlist(payload: WatchlistCreate, db: DbSession) -> Watchlist:
    wl = Watchlist(name=payload.name, description=payload.description)
    wl.items = [
        WatchlistItem(ticker=i.ticker.upper(), exchange=i.exchange, weight=i.weight)
        for i in payload.items
    ]
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


@router.get("/{watchlist_id}", response_model=WatchlistOut)
def get_watchlist(watchlist_id: int, db: DbSession) -> Watchlist:
    wl = db.get(Watchlist, watchlist_id)
    if not wl:
        raise HTTPException(404, "watchlist not found")
    return wl


@router.post("/{watchlist_id}/items", response_model=WatchlistOut)
def add_item(watchlist_id: int, ticker: str, db: DbSession, exchange: str = "NSE",
             weight: float = 1.0) -> Watchlist:
    wl = db.get(Watchlist, watchlist_id)
    if not wl:
        raise HTTPException(404, "watchlist not found")
    wl.items.append(WatchlistItem(ticker=ticker.upper(), exchange=exchange, weight=weight))
    db.commit()
    db.refresh(wl)
    return wl


@router.delete("/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: int, db: DbSession) -> None:
    wl = db.get(Watchlist, watchlist_id)
    if wl:
        db.delete(wl)
        db.commit()
