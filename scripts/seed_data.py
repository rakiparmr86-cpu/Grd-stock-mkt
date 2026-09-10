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
from app.core.security import hash_password
from app.models.config import Rule, Strategy, Threshold, Watchlist, WatchlistItem
from app.models.inputs import InputSource
from app.models.market import Instrument
from app.models.user import User

DEMO_EMAIL = "demo@grd-stk-mkt.local"
DEMO_PASSWORD = "1223456"

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

    # demo login (idempotent — always ensured)
    with session_scope() as db:
        user = db.execute(
            select(User).where(User.email == DEMO_EMAIL)
        ).scalar_one_or_none()
        if user is None:
            db.add(User(email=DEMO_EMAIL, full_name="Demo User",
                        hashed_password=hash_password(DEMO_PASSWORD), is_superuser=True))
            print(f"  demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"  demo user already exists: {DEMO_EMAIL}")

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

        # demo input sources (pluggable connectors)
        db.add(InputSource(
            name="Seed CSVs", connector="csv", kind="rows", is_active=True,
            config={"dir": "./data/market", "glob": "*.csv", "row_kind": "ohlcv"},
        ))
        db.add(InputSource(
            name="Local documents (PDF)", connector="pdf", kind="docs", is_active=True,
            config={"dir": "./data/documents", "glob": "**/*.pdf"},
        ))
        db.add(InputSource(
            name="GRD console (example, disabled)", connector="web_crawler",
            kind="docs", is_active=False,
            config={
                "start_urls": ["https://console.grdworld.com/Schedular/Index"],
                "max_depth": 1, "max_pages": 20, "respect_robots": True,
                "include_patterns": ["/Schedular/"],
                "auth": {"type": "form_login",
                         "login_url": "https://console.grdworld.com/Account/Login",
                         "user_field": "Email", "password_field": "Password",
                         "user_env": "GRDWORLD_USER", "password_env": "GRDWORLD_PASS"},
            },
        ))

    print("  seeded watchlist + strategy + rules + input sources")
    print("\nNext:")
    print("  uvicorn app.main:app --reload")
    print(f"  # log in as {DEMO_EMAIL} / {DEMO_PASSWORD} (frontend, or:)")
    print("  curl -s -X POST localhost:8000/api/v1/auth/login \\")
    print(f"       -d 'username={DEMO_EMAIL}&password={DEMO_PASSWORD}'")
    print("  # then send the token as: -H 'Authorization: Bearer <access_token>'")


if __name__ == "__main__":
    main()
