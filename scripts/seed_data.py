"""Seed demo config + synthetic market data so the pipeline runs end-to-end.

    python scripts/seed_data.py

Creates:
  * a watchlist (RELIANCE, TCS, INFY)
  * a "Mean reversion + trend" strategy with three rules
  * synthetic daily OHLCV CSVs under data/market/ (used by the CSV provider)
  * one plain-text research note under data/documents/
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.database import session_scope
from app.models.config import Rule, Strategy, Threshold, Watchlist, WatchlistItem
from app.models.market import Instrument

TICKERS = ["RELIANCE", "TCS", "INFY"]
MARKET_DIR = Path("./data/market")
DOC_DIR = Path("./data/documents")


def _synthetic_ohlcv(ticker: str, days: int = 500, seed: int = 0) -> str:
    random.seed(hash(ticker) ^ seed)
    price = random.uniform(800, 2500)
    start = datetime.utcnow() - timedelta(days=days)
    lines = ["date,open,high,low,close,volume"]
    for i in range(days):
        drift = 0.0004
        shock = random.gauss(0, 0.018)
        cycle = 0.01 * math.sin(i / 21.0)
        ret = drift + shock + cycle
        open_ = price
        close = max(1.0, price * (1 + ret))
        high = max(open_, close) * (1 + abs(random.gauss(0, 0.006)))
        low = min(open_, close) * (1 - abs(random.gauss(0, 0.006)))
        vol = int(abs(random.gauss(1_000_000, 350_000)))
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(f"{d},{open_:.2f},{high:.2f},{low:.2f},{close:.2f},{vol}")
        price = close
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    path = MARKET_DIR / f"{ticker}.csv"
    path.write_text("\n".join(lines))
    return str(path)


# ── rule expressions (JSON AST understood by app.services.signals.engine) ──
RULES = [
    {
        "name": "Overse RSI bounce",
        "signal_type": "buy",
        "priority": 10,
        "expression": {
            "op": "and",
            "args": [
                {"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 35}},
                {"op": "gt", "left": {"indicator": "close"},
                 "right": {"indicator": "sma_200"}},
            ],
        },
    },
    {
        "name": "EMA20 crosses above EMA50",
        "signal_type": "buy",
        "priority": 20,
        "expression": {
            "op": "cross_up",
            "left": {"indicator": "ema_20"},
            "right": {"indicator": "ema_50"},
        },
    },
    {
        "name": "Overbought + high volume -> alert",
        "signal_type": "alert",
        "priority": 30,
        "expression": {
            "op": "and",
            "args": [
                {"op": "gt", "left": {"indicator": "rsi_14"}, "right": {"const": 72}},
                {"op": "gt", "left": {"indicator": "volume_ratio_20"},
                 "right": {"const": 1.8}},
            ],
        },
    },
]


def main() -> None:
    for t in TICKERS:
        p = _synthetic_ohlcv(t)
        print(f"  wrote {p}")

    DOC_DIR.mkdir(parents=True, exist_ok=True)
    note = DOC_DIR / "RELIANCE_note.txt"
    note.write_text(
        "RELIANCE research note.\n\n"
        "Management guided to double-digit revenue growth in the retail segment "
        "and continued capex in new energy. Key risks: refining margin volatility "
        "and regulatory changes in telecom tariffs. Balance sheet deleveraging on "
        "track after the recent rights issue.\n"
    )
    print(f"  wrote {note}")

    with session_scope() as db:
        if db.execute(select(Strategy).where(Strategy.name == "Mean reversion + trend")
                      ).scalar_one_or_none():
            print("  strategy already seeded — skipping DB writes")
            return

        for t in TICKERS:
            db.add(Instrument(ticker=t, exchange="NSE", name=t.title()))

        wl = Watchlist(name="Core NSE", description="Demo watchlist")
        wl.items = [WatchlistItem(ticker=t) for t in TICKERS]
        db.add(wl)

        strat = Strategy(
            name="Mean reversion + trend",
            description="RSI mean-reversion filtered by long-term trend, plus EMA cross.",
            params={"analysts": ["technical_analyst", "fundamental_analyst", "rag_research"],
                    "use_fundamentals": True},
        )
        strat.rules = [Rule(**r) for r in RULES]
        strat.thresholds = [Threshold(key="min_conviction", value=0.2)]
        db.add(strat)

    print("  seeded watchlist + strategy + rules")
    print("\nNext:")
    print("  uvicorn app.main:app --reload")
    print("  curl -X POST localhost:8000/api/v1/runs -H 'content-type: application/json' \\")
    print('       -d \'{"ticker":"RELIANCE","strategy_id":1,"async_":false}\'')


if __name__ == "__main__":
    main()
