"""SQLAlchemy models. Import everything here so Alembic autogenerate sees them."""

from app.models.base import Base
from app.models.config import (
    Rule,
    Schedule,
    Strategy,
    Threshold,
    Watchlist,
    WatchlistItem,
)
from app.models.history import AgentDecision, Alert, AnalysisRun, Report, Signal
from app.models.market import Fundamental, IndicatorPoint, Instrument, OHLCV
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Watchlist",
    "WatchlistItem",
    "Strategy",
    "Rule",
    "Threshold",
    "Schedule",
    "Instrument",
    "OHLCV",
    "Fundamental",
    "IndicatorPoint",
    "AnalysisRun",
    "Signal",
    "Report",
    "Alert",
    "AgentDecision",
]
