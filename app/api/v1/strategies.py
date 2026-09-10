from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.models.config import Rule, Strategy, Threshold
from app.schemas.config import StrategyCreate, StrategyOut

router = APIRouter()


@router.get("", response_model=list[StrategyOut])
def list_strategies(db: DbSession) -> list[Strategy]:
    return list(
        db.execute(select(Strategy).options(selectinload(Strategy.rules))).scalars()
    )


@router.post("", response_model=StrategyOut, status_code=201)
def create_strategy(payload: StrategyCreate, db: DbSession) -> Strategy:
    if db.execute(select(Strategy).where(Strategy.name == payload.name)).scalar_one_or_none():
        raise HTTPException(409, "strategy name already exists")
    strat = Strategy(name=payload.name, description=payload.description, params=payload.params)
    strat.rules = [
        Rule(name=r.name, signal_type=r.signal_type, expression=r.expression,
             priority=r.priority, cooldown_minutes=r.cooldown_minutes, is_active=r.is_active)
        for r in payload.rules
    ]
    strat.thresholds = [
        Threshold(key=k, value=v) for k, v in payload.thresholds.items()
    ]
    db.add(strat)
    db.commit()
    db.refresh(strat)
    return strat


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: int, db: DbSession) -> Strategy:
    strat = db.get(Strategy, strategy_id)
    if not strat:
        raise HTTPException(404, "strategy not found")
    return strat


@router.patch("/{strategy_id}/active", response_model=StrategyOut)
def set_active(strategy_id: int, active: bool, db: DbSession) -> Strategy:
    strat = db.get(Strategy, strategy_id)
    if not strat:
        raise HTTPException(404, "strategy not found")
    strat.is_active = active
    db.commit()
    db.refresh(strat)
    return strat
