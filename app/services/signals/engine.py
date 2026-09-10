"""Dynamic rule / signal engine.

Rules are stored in the DB as a small JSON AST and evaluated here against the
output of the calculation engine. No ``eval`` — every operator is explicit.

Grammar
-------
operand  := {"const": <number|str|bool>}
          | {"indicator": "<name>"}          # current bar
          | {"indicator": "<name>", "offset": <int>}   # N bars back
          | {"price": "close" | "open" | ...}

expr     := operand-comparison | boolean-combination
comparison := {"op": "gt"|"lt"|"gte"|"lte"|"eq"|"ne",
               "left": <operand>, "right": <operand>}
cross    := {"op": "cross_up"|"cross_down",
             "left": <operand>, "right": <operand>}   # needs series
combo    := {"op": "and"|"or"|"not", "args": [<expr>, ...]}
between  := {"op": "between", "value": <operand>, "low": <operand>, "high": <operand>}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

_COMPARATORS = {
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


class RuleEvaluationError(ValueError):
    pass


@dataclass
class RuleMatch:
    matched: bool
    strength: float
    detail: dict[str, Any]


class _Context:
    """Everything a rule can reference for one ticker at one point in time."""

    def __init__(self, latest: dict[str, float], frame: pd.DataFrame | None = None) -> None:
        self.latest = latest
        self.frame = frame

    def indicator(self, name: str, offset: int = 0) -> float:
        if offset == 0:
            if name not in self.latest or self.latest[name] is None:
                raise RuleEvaluationError(f"indicator {name!r} not available")
            return float(self.latest[name])
        if self.frame is None or name not in self.frame.columns:
            raise RuleEvaluationError(f"series for {name!r} not available (offset={offset})")
        return float(self.frame[name].iloc[-1 - offset])

    def series(self, name: str) -> pd.Series:
        if self.frame is None or name not in self.frame.columns:
            raise RuleEvaluationError(f"series for {name!r} not available")
        return self.frame[name]


def _operand(node: dict[str, Any], ctx: _Context) -> Any:
    if "const" in node:
        return node["const"]
    if "indicator" in node:
        return ctx.indicator(node["indicator"], int(node.get("offset", 0)))
    if "price" in node:
        return ctx.indicator("close") if node["price"] == "close" else ctx.indicator(node["price"])
    raise RuleEvaluationError(f"bad operand: {node!r}")


def _eval(node: dict[str, Any], ctx: _Context, trace: list[dict[str, Any]]) -> bool:
    op = node.get("op")
    if op is None:
        raise RuleEvaluationError(f"missing 'op' in {node!r}")

    if op in ("and", "or"):
        results = [_eval(a, ctx, trace) for a in node["args"]]
        return all(results) if op == "and" else any(results)
    if op == "not":
        return not _eval(node["args"][0], ctx, trace)

    if op in _COMPARATORS:
        left = _operand(node["left"], ctx)
        right = _operand(node["right"], ctx)
        ok = bool(_COMPARATORS[op](left, right))
        trace.append({"op": op, "left": left, "right": right, "matched": ok})
        return ok

    if op == "between":
        v = _operand(node["value"], ctx)
        lo = _operand(node["low"], ctx)
        hi = _operand(node["high"], ctx)
        ok = lo <= v <= hi
        trace.append({"op": op, "value": v, "low": lo, "high": hi, "matched": ok})
        return ok

    if op in ("cross_up", "cross_down"):
        left = _resolve_series(node["left"], ctx)
        right = _resolve_series(node["right"], ctx)
        if len(left) < 2 or len(right) < 2:
            return False
        prev = left.iloc[-2] - right.iloc[-2]
        curr = left.iloc[-1] - right.iloc[-1]
        ok = (prev <= 0 < curr) if op == "cross_up" else (prev >= 0 > curr)
        trace.append({"op": op, "prev_diff": float(prev), "curr_diff": float(curr),
                      "matched": ok})
        return ok

    raise RuleEvaluationError(f"unknown op: {op!r}")


def _resolve_series(node: dict[str, Any], ctx: _Context) -> pd.Series:
    if "indicator" in node:
        return ctx.series(node["indicator"])
    if "price" in node:
        return ctx.series("close" if node["price"] == "close" else node["price"])
    if "const" in node:
        # broadcast a constant to match index length
        base = ctx.frame if ctx.frame is not None else pd.Series([node["const"]])
        return pd.Series(node["const"], index=getattr(base, "index", [0]))
    raise RuleEvaluationError(f"cross operand needs a series: {node!r}")


def evaluate_rule(
    expression: dict[str, Any],
    latest: dict[str, float],
    frame: pd.DataFrame | None = None,
) -> RuleMatch:
    ctx = _Context(latest, frame)
    trace: list[dict[str, Any]] = []
    matched = _eval(expression, ctx, trace)
    hits = sum(1 for t in trace if t.get("matched"))
    strength = round(hits / len(trace), 3) if trace else (1.0 if matched else 0.0)
    return RuleMatch(matched=matched, strength=strength if matched else 0.0,
                     detail={"trace": trace})


@dataclass
class EngineResult:
    ticker: str
    signals: list[dict[str, Any]]


class SignalEngine:
    """Evaluate a set of active rules for one ticker."""

    def __init__(self, rules: list[Any]) -> None:
        # rules: iterable of objects with .id .name .signal_type .expression .priority
        self.rules = sorted(rules, key=lambda r: getattr(r, "priority", 100))

    def evaluate(
        self,
        ticker: str,
        latest: dict[str, float],
        frame: pd.DataFrame | None = None,
    ) -> EngineResult:
        out: list[dict[str, Any]] = []
        for rule in self.rules:
            if not getattr(rule, "is_active", True):
                continue
            try:
                match = evaluate_rule(rule.expression, latest, frame)
            except RuleEvaluationError as exc:
                out.append({"rule_id": getattr(rule, "id", None), "rule": rule.name,
                            "error": str(exc), "matched": False})
                continue
            if match.matched:
                out.append(
                    {
                        "rule_id": getattr(rule, "id", None),
                        "rule": rule.name,
                        "signal_type": rule.signal_type,
                        "strength": match.strength,
                        "price": latest.get("close"),
                        "detail": match.detail,
                        "matched": True,
                    }
                )
        return EngineResult(ticker=ticker, signals=out)
