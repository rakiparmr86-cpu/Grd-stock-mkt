from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories import (
    AgentDecisionRepository,
    AlertRepository,
    ExceptionLogRepository,
    IngestionRunRepository,
    InputSourceRepository,
    ReportRepository,
    RuleRepository,
    SignalRepository,
    StrategyRepository,
    UserRepository,
    WatchlistRepository,
)
from app.repositories.run import AnalysisRunRepository

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login", auto_error=False
)

DbSession = Annotated[Session, Depends(get_db)]


# ── repositories, one per aggregate root — see app/repositories/base.py ────
def get_user_repo(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_watchlist_repo(db: DbSession) -> WatchlistRepository:
    return WatchlistRepository(db)


def get_strategy_repo(db: DbSession) -> StrategyRepository:
    return StrategyRepository(db)


def get_rule_repo(db: DbSession) -> RuleRepository:
    return RuleRepository(db)


def get_input_source_repo(db: DbSession) -> InputSourceRepository:
    return InputSourceRepository(db)


def get_run_repo(db: DbSession) -> AnalysisRunRepository:
    return AnalysisRunRepository(db)


def get_signal_repo(db: DbSession) -> SignalRepository:
    return SignalRepository(db)


def get_report_repo(db: DbSession) -> ReportRepository:
    return ReportRepository(db)


def get_agent_decision_repo(db: DbSession) -> AgentDecisionRepository:
    return AgentDecisionRepository(db)


def get_alert_repo(db: DbSession) -> AlertRepository:
    return AlertRepository(db)


def get_exception_log_repo(db: DbSession) -> ExceptionLogRepository:
    return ExceptionLogRepository(db)


def get_ingestion_run_repo(db: DbSession) -> IngestionRunRepository:
    return IngestionRunRepository(db)


UserRepo = Annotated[UserRepository, Depends(get_user_repo)]
WatchlistRepo = Annotated[WatchlistRepository, Depends(get_watchlist_repo)]
StrategyRepo = Annotated[StrategyRepository, Depends(get_strategy_repo)]
RuleRepo = Annotated[RuleRepository, Depends(get_rule_repo)]
InputSourceRepo = Annotated[InputSourceRepository, Depends(get_input_source_repo)]
RunRepo = Annotated[AnalysisRunRepository, Depends(get_run_repo)]
SignalRepo = Annotated[SignalRepository, Depends(get_signal_repo)]
ReportRepo = Annotated[ReportRepository, Depends(get_report_repo)]
AgentDecisionRepo = Annotated[AgentDecisionRepository, Depends(get_agent_decision_repo)]
AlertRepo = Annotated[AlertRepository, Depends(get_alert_repo)]
ExceptionLogRepo = Annotated[ExceptionLogRepository, Depends(get_exception_log_repo)]
IngestionRunRepo = Annotated[IngestionRunRepository, Depends(get_ingestion_run_repo)]


# ── auth ────────────────────────────────────────────────────────────────
def _user_for_token(users: UserRepo, token: str | None) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise cred_exc
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception as exc:  # noqa: BLE001
        raise cred_exc from exc
    user = users.get(user_id)
    if user is None or not user.is_active:
        raise cred_exc
    return user


def get_current_user(
    users: UserRepo,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    return _user_for_token(users, token)


def get_export_user(
    users: UserRepo,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    access_token: str | None = None,
) -> User:
    """Like ``get_current_user`` but also accepts ``?access_token=``: a browser
    or phone opening a download link cannot attach an Authorization header."""
    return _user_for_token(users, token or access_token)


CurrentUser = Annotated[User, Depends(get_current_user)]
