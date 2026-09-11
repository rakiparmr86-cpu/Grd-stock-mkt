"""Data-access layer: one repository per aggregate root, wrapping a Session.

See ``base.py`` for the convention. Routers get repos via ``app/api/deps.py``
dependencies; Celery tasks / services build them directly from a
``session_scope()`` session.
"""

from app.repositories.agent_decision import AgentDecisionRepository
from app.repositories.alert import AlertRepository
from app.repositories.base import BaseRepository
from app.repositories.input_source import InputSourceRepository
from app.repositories.instrument import InstrumentRepository
from app.repositories.report import ReportRepository
from app.repositories.rule import RuleRepository
from app.repositories.run import AnalysisRunRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.signal import SignalRepository
from app.repositories.strategy import StrategyRepository
from app.repositories.user import UserRepository
from app.repositories.watchlist import WatchlistRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "WatchlistRepository",
    "StrategyRepository",
    "RuleRepository",
    "InputSourceRepository",
    "AnalysisRunRepository",
    "SignalRepository",
    "ReportRepository",
    "AgentDecisionRepository",
    "AlertRepository",
    "ScheduleRepository",
    "InstrumentRepository",
]
