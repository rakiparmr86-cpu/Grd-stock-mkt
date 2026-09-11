from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession, StrategyRepo
from app.models.config import Rule, Strategy, Threshold
from app.schemas.config import StrategyCreate, StrategyOut

router = APIRouter()


@router.get("", response_model=list[StrategyOut])
def list_strategies(strategies: StrategyRepo) -> list[Strategy]:
    return strategies.list_with_rules()


@router.post("", response_model=StrategyOut, status_code=201)
def create_strategy(payload: StrategyCreate, db: DbSession, strategies: StrategyRepo) -> Strategy:
    if strategies.by_name(payload.name):
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
    strategies.add(strat)
    db.commit()
    db.refresh(strat)
    return strat


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: int, strategies: StrategyRepo) -> Strategy:
    strat = strategies.get(strategy_id)
    if not strat:
        raise HTTPException(404, "strategy not found")
    return strat


@router.patch("/{strategy_id}/active", response_model=StrategyOut)
def set_active(strategy_id: int, active: bool, db: DbSession, strategies: StrategyRepo) -> Strategy:
    strat = strategies.get(strategy_id)
    if not strat:
        raise HTTPException(404, "strategy not found")
    strat.is_active = active
    db.commit()
    db.refresh(strat)
    return strat
