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


UserRepo = Annotated[UserRepository, Depends(get_user_repo)]
WatchlistRepo = Annotated[WatchlistRepository, Depends(get_watchlist_repo)]
StrategyRepo = Annotated[StrategyRepository, Depends(get_strategy_repo)]
RuleRepo = Annotated[RuleRepository, Depends(get_rule_repo)]
InputSourceRepo = Annotated[InputSourceRepository, Depends(get_input_source_repo)]
RunRepo = Annotated[AnalysisRunRepository, Depends(get_run_repo)]
SignalRepo = Annotated[SignalRepository, Depends(get_signal_repo)]
ReportRepo = Annotated[ReportRepository, Depends(get_report_repo)]
AgentDecisionRepo = Annotated[AgentDecisionRepository, Depends(get_agent_decision_repo)]


# ── auth ────────────────────────────────────────────────────────────────
def get_current_user(
    users: UserRepo,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
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


CurrentUser = Annotated[User, Depends(get_current_user)]
