from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import DbSession, RuleRepo
from app.models.config import Rule
from app.schemas.config import RuleCreate, RuleOut
from app.services.signals.engine import RuleEvaluationError, evaluate_rule

router = APIRouter()


@router.get("", response_model=list[RuleOut])
def list_rules(rules: RuleRepo, strategy_id: int | None = None) -> list[Rule]:
    return rules.list_for_strategy(strategy_id)


@router.post("/strategy/{strategy_id}", response_model=RuleOut, status_code=201)
def add_rule(strategy_id: int, payload: RuleCreate, db: DbSession, rules: RuleRepo) -> Rule:
    rule = rules.add(Rule(strategy_id=strategy_id, **payload.model_dump()))
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, payload: RuleCreate, db: DbSession, rules: RuleRepo) -> Rule:
    rule = rules.get(rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: DbSession, rules: RuleRepo) -> None:
    rule = rules.get(rule_id)
    if rule:
        rules.delete(rule)
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
