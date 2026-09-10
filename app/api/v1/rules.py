from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.config import Rule
from app.schemas.config import RuleCreate, RuleOut
from app.services.signals.engine import RuleEvaluationError, evaluate_rule

router = APIRouter()


@router.get("", response_model=list[RuleOut])
def list_rules(db: DbSession, strategy_id: int | None = None) -> list[Rule]:
    q = select(Rule)
    if strategy_id is not None:
        q = q.where(Rule.strategy_id == strategy_id)
    return list(db.execute(q).scalars())


@router.post("/strategy/{strategy_id}", response_model=RuleOut, status_code=201)
def add_rule(strategy_id: int, payload: RuleCreate, db: DbSession) -> Rule:
    rule = Rule(strategy_id=strategy_id, **payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, payload: RuleCreate, db: DbSession) -> Rule:
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: DbSession) -> None:
    rule = db.get(Rule, rule_id)
    if rule:
        db.delete(rule)
        db.commit()


class RuleTestIn(BaseModel):
    expression: dict[str, Any]
    indicators: dict[str, float]


@router.post("/test")
def test_rule(payload: RuleTestIn) -> dict:
    try:
        match = evaluate_rule(payload.expression, payload.indicators)
    except RuleEvaluationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"matched": match.matched, "strength": match.strength, "detail": match.detail}
