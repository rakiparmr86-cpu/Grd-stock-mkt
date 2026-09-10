from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from app.services.signals.engine import RuleEvaluationError, SignalEngine, evaluate_rule


@dataclass
class FakeRule:
    id: int
    name: str
    signal_type: str
    expression: dict
    priority: int = 100
    is_active: bool = True


def test_simple_comparison_true():
    m = evaluate_rule({"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 30}},
                      {"rsi_14": 22.0})
    assert m.matched and m.strength == 1.0


def test_and_combination_partial_fails():
    expr = {"op": "and", "args": [
        {"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 30}},
        {"op": "gt", "left": {"indicator": "close"}, "right": {"indicator": "sma_200"}},
    ]}
    m = evaluate_rule(expr, {"rsi_14": 22.0, "close": 90.0, "sma_200": 100.0})
    assert not m.matched


def test_or_combination():
    expr = {"op": "or", "args": [
        {"op": "gt", "left": {"indicator": "rsi_14"}, "right": {"const": 90}},
        {"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 30}},
    ]}
    assert evaluate_rule(expr, {"rsi_14": 12.0}).matched


def test_between_operator():
    expr = {"op": "between", "value": {"indicator": "rsi_14"},
            "low": {"const": 40}, "high": {"const": 60}}
    assert evaluate_rule(expr, {"rsi_14": 50.0}).matched
    assert not evaluate_rule(expr, {"rsi_14": 65.0}).matched


def test_cross_up_needs_series():
    frame = pd.DataFrame({"ema_20": [1, 2, 3, 4, 6], "ema_50": [5, 5, 5, 5, 5]})
    expr = {"op": "cross_up", "left": {"indicator": "ema_20"}, "right": {"indicator": "ema_50"}}
    assert evaluate_rule(expr, {"ema_20": 6, "ema_50": 5}, frame).matched


def test_missing_indicator_raises():
    with pytest.raises(RuleEvaluationError):
        evaluate_rule({"op": "lt", "left": {"indicator": "nope"}, "right": {"const": 1}}, {})


def test_engine_orders_by_priority_and_filters_inactive():
    rules = [
        FakeRule(1, "hi", "buy", {"op": "gt", "left": {"indicator": "x"},
                                  "right": {"const": 0}}, priority=50),
        FakeRule(2, "off", "buy", {"op": "gt", "left": {"indicator": "x"},
                                   "right": {"const": 0}}, priority=1, is_active=False),
    ]
    res = SignalEngine(rules).evaluate("TEST", {"x": 5.0})
    assert [s["rule_id"] for s in res.signals if s["matched"]] == [1]
