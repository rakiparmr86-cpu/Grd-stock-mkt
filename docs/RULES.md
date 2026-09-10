# RULES.md — signal-rule cookbook

Copy-paste `expression` values for the `rules` table / `POST /api/v1/rules`.
Full grammar and evaluation semantics: [TECHNICAL.md](TECHNICAL.md) §5.

## 30-second recap

An expression is a small JSON tree. Operands:

```jsonc
{"const": 30}                      // literal
{"indicator": "rsi_14"}            // current bar
{"indicator": "ema_20", "offset": 1}   // 1 bar ago (needs history)
{"price": "close"}                 // = {"indicator": "close"}
```

Operators: `gt lt gte lte eq ne` · `and or not` (`args: [...]`) · `between`
(`value/low/high`) · `cross_up` `cross_down` (series).

Indicator names available by default (from `DEFAULT_SPEC`): `close`, `sma_20`,
`sma_50`, `sma_200`, `ema_20`, `ema_50`, `rsi_14`, `macd`, `macd_signal`,
`macd_hist`, `atr_14`, `volume_ratio_20`, `returns_1`, `returns_5`,
`volatility_20`, `bb_upper`, `bb_mid`, `bb_lower`. Add more via
`strategy.params["indicators"]`.

Test any expression without saving:

```bash
curl -X POST localhost:8000/api/v1/rules/test -H "content-type: application/json" \
  -d '{"expression": {"op":"lt","left":{"indicator":"rsi_14"},"right":{"const":30}},
       "indicators": {"rsi_14": 24.1}}'
```

---

## Momentum / mean reversion

**RSI oversold** — `signal_type: "buy"`
```json
{"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 30}}
```

**RSI oversold, but only in an uptrend** (price above the 200-day)
```json
{"op": "and", "args": [
  {"op": "lt", "left": {"indicator": "rsi_14"}, "right": {"const": 35}},
  {"op": "gt", "left": {"indicator": "close"}, "right": {"indicator": "sma_200"}}
]}
```

**RSI overbought → alert** — `signal_type: "alert"`
```json
{"op": "gt", "left": {"indicator": "rsi_14"}, "right": {"const": 70}}
```

**RSI back in the neutral band** (exited oversold)
```json
{"op": "between", "value": {"indicator": "rsi_14"},
 "low": {"const": 40}, "high": {"const": 55}}
```

## Trend / crossovers

**Golden cross** — EMA20 crosses above EMA50 — `signal_type: "buy"`
```json
{"op": "cross_up", "left": {"indicator": "ema_20"}, "right": {"indicator": "ema_50"}}
```

**Death cross** — EMA20 crosses below EMA50 — `signal_type: "sell"`
```json
{"op": "cross_down", "left": {"indicator": "ema_20"}, "right": {"indicator": "ema_50"}}
```

**Price reclaims the 200-day** (was below yesterday, above today)
```json
{"op": "and", "args": [
  {"op": "lt", "left": {"indicator": "close", "offset": 1}, "right": {"indicator": "sma_200", "offset": 1}},
  {"op": "gt", "left": {"indicator": "close"}, "right": {"indicator": "sma_200"}}
]}
```

**MACD turns positive** (histogram crosses zero up)
```json
{"op": "cross_up", "left": {"indicator": "macd_hist"}, "right": {"const": 0}}
```

## Breakouts / volatility

**Bollinger breakout with volume confirmation** — `signal_type: "buy"`
```json
{"op": "and", "args": [
  {"op": "gt", "left": {"indicator": "close"}, "right": {"indicator": "bb_upper"}},
  {"op": "gt", "left": {"indicator": "volume_ratio_20"}, "right": {"const": 1.5}}
]}
```

**Volatility spike → alert**
```json
{"op": "gt", "left": {"indicator": "volatility_20"}, "right": {"const": 0.6}}
```

**Sharp one-day drop** (down more than 5% today) — `signal_type: "alert"`
```json
{"op": "lt", "left": {"indicator": "returns_1"}, "right": {"const": -0.05}}
```

## Combined example (a small strategy)

Buy when **all** hold: oversold-ish, uptrend intact, momentum turning, volume there.
```json
{"op": "and", "args": [
  {"op": "lt",  "left": {"indicator": "rsi_14"},          "right": {"const": 40}},
  {"op": "gt",  "left": {"indicator": "close"},           "right": {"indicator": "sma_200"}},
  {"op": "gt",  "left": {"indicator": "macd_hist"},       "right": {"const": 0}},
  {"op": "gte", "left": {"indicator": "volume_ratio_20"}, "right": {"const": 1.0}}
]}
```

---

## Notes & gotchas

- `offset` and `cross_*` need price **history**, which the engine has during a
  real run (`calc.frame`) but **not** in `POST /rules/test` (latest values only)
  — a `cross_*` there returns `false`.
- An indicator that isn't in the spec raises a rule error; the engine records it
  under that rule's `error` and keeps evaluating the others.
- `strength` in a fired signal = fraction of leaf comparisons that were true —
  useful for ranking, not a probability.
- `signal_type` (`buy` / `sell` / `alert`) is a column on the rule, **not** part
  of `expression`.
- `cooldown_minutes` is stored but **not yet enforced** (see TECHNICAL §17).
- Rules are evaluated in ascending `priority`; lower runs first.
