# Analysis methods: tools, techniques and statistics

What the platform computes, how, and with which Python library. Almost everything is **plain Python maths**. The LLM (OpenAI) is optional and only writes narrative text. Scores, signals, forecasts, ratios and verdicts never depend on it.

| Layer | Libraries |
|---|---|
| Data handling | `pandas`, `numpy`, `openpyxl` (Excel) |
| Statistics / forecasting | `statsmodels` (OLS, ETS, ARIMA), `scikit-learn` (Ridge, Lasso), `scipy` (normal quantiles) |
| Document search | Qdrant vector DB, cosine similarity, hashing or OpenAI embeddings |
| Agent orchestration | LangGraph |
| Reports | Jinja2 (HTML), `matplotlib` (chart), `openpyxl` (Excel) |

The five analyses below are independent. Which one runs depends on what you press.

---

## 1. Technical analysis (price data)

Needs at least 30 daily OHLCV bars. Code: `app/services/calculations/indicators.py`, `engine.py`.

| Indicator | Method | Default |
|---|---|---|
| SMA | simple rolling mean of close | 20, 50, 200 |
| EMA | exponentially weighted mean | span-based |
| RSI | Wilder smoothing (EWM, alpha = 1/period) of average gain / average loss | 14 |
| MACD | EMA(12) − EMA(26); signal = EMA(9) of that; histogram = difference | 12/26/9 |
| ATR | Wilder-smoothed true range | 14 |
| Volume ratio | today's volume / 20-day average volume | 20 |
| Volatility | rolling std of returns, annualized (× √252) | 20-day |
| Bollinger bands | SMA ± 2 std | 20, 2.0 |

### Rule / signal engine (`app/services/signals/engine.py`)
Rules are stored as a small JSON expression tree (compare, `cross_up`/`cross_down`, `between`, `and`/`or`/`not`). It is evaluated without `eval`. A rule fires when its expression is true on the latest bar. Examples are in `docs/RULES.md`.

### Technical analyst agent score (deterministic)
Score is the sum, clipped to [-1, 1]:

| Condition | Points |
|---|---|
| close vs SMA20 / SMA50 / SMA200 | ±0.15 / ±0.15 / ±0.20 |
| RSI < 30 (oversold) / > 70 (overbought) | +0.15 / −0.15 |
| MACD histogram positive / negative | +0.15 / −0.15 |
| volume ratio > 1.5 | +0.10 |

Stance: score > 0.2 bullish, < −0.2 bearish, otherwise neutral.

---

## 2. Fundamental analysis (statements)

Uses rows in the `fundamentals` table (from a Screener-style Excel loaded as rows).

### Single-period score (`fundamental_analyst.py`)

| Metric | Points |
|---|---|
| P/E < 15 / > 40 | +0.25 / −0.25 |
| Debt/equity < 0.5 / > 2 | +0.20 / −0.20 |
| Net margin > 10% / otherwise | +0.15 / −0.10 |

Stance: > 0.2 cheap, < −0.2 expensive, otherwise fair.

### Statistical engine (`calculations/statistics.py`)
Runs when there are 4 or more periods of revenue and net income.

| Technique | Method |
|---|---|
| Descriptive stats | mean, median, std, variance, percentiles (5–95), skew, kurtosis |
| Outlier flag | **MAD-based modified z-score** `0.6745·(x−median)/MAD`, flagged when \|z\| > 3.5. It is robust because an outlier cannot inflate its own std |
| Growth | YoY (period-over-period, or 4 back for quarterly), QoQ, **CAGR** `(last/first)^(1/years) − 1`, rolling mean, EWMA. CAGR is undefined for non-positive endpoints |
| Correlation | Pearson or Spearman matrix, sorted by strength. Screening only, not causal |
| Regression | **OLS** (statsmodels) with coefficients, p-values, 95% CI, R²; or **Ridge / Lasso** (scikit-learn, standardized features). Used as net income ~ revenue |
| Forecast | **ETS** (Holt-Winters, additive trend) or **ARIMA(1,1,1) / SARIMA**; 95% confidence interval via the normal quantile. Refuses to fit with fewer than 4 periods, and refuses a seasonal model without 2 full cycles |
| Risk | volatility, **downside deviation**, **max drawdown**, current drawdown |
| Backtest | **walk-forward**: refit on each expanding window, predict the next point, report RMSE, MAPE and directional hit-rate |

The default report forecasts 5 years ahead for revenue and net income. The widening confidence interval in later years is the model showing it is less certain.

### Ratio report (`calculations/ratios.py`)

| Group | Ratios |
|---|---|
| Margins | operating margin (OPM), net margin, NIM (lenders only, approximated) |
| Returns | ROE = net profit / equity; ROA; ROCE |
| Valuation | P/E, P/B (price / book value per share), EV/EBITDA, EV/Sales (EV ≈ market cap + borrowings) |
| Quality | cash conversion (operating cash flow / net profit), debt/equity, gross NPA or asset turnover |

Any ratio with missing inputs returns `insufficient_data` and a reason, instead of a guess.

---

## 3. Document research (RAG)

For PDFs, images (OCR) and Excel-as-documents.

1. **Parse** to text.
2. **Chunk**: about 350 words per chunk with 60-word overlap.
3. **Embed**: a local hashing embedder (no network) or OpenAI embeddings. Configured by `EMBEDDINGS_PROVIDER`.
4. **Store** in Qdrant with the ticker and document type as filters.
5. **Retrieve**: top 6 chunks by **cosine similarity**. It searches ticker-tagged chunks first, then any indexed chunk.
6. The RAG agent summarizes the hits (LLM, if configured) and returns citations with scores.

The local hashing embedder is a word-count hash, so it matches shared words, not meaning. Use OpenAI embeddings for real semantic search.

---

## 4. Risk critic and final verdict (`risk_critic.py`, `report_writer.py`)

**Conviction** is the weighted average of the analysts' scores (technical 0.45, fundamental 0.35, RAG 0.20). Analysts with no data are excluded and the weights are re-normalised.

**Risk flags:**
- annualized volatility above 60%
- a buy signal while RSI is above 70
- technical stance and fundamental stance disagree

**Verdict:** `go` if conviction > 0.35 with no flags, `caution` if conviction > 0.15, otherwise `no-go`.

**Action:** go → BUY, caution → HOLD, no-go → AVOID. A conflicting `sell` signal downgrades BUY to HOLD.

---

## 5. Prediction report for Screener workbooks (no LLM)

Used by "Analyze document" on a Screener workbook. Code: `app/services/reports/prediction_report.py`. Layout follows `GRDPrediction_Model.xlsx`.

**Inputs (from the workbook):**
- TTM sales and net profit: sum of the last 4 quarters
- TTM EPS: TTM net profit / shares, where shares = last FY net profit / last FY EPS
- P/E: current price / TTM EPS
- ROE: net profit / (equity capital + reserves)
- Latest quarter year-on-year growth: 4 quarters back
- TTM operating margin

**Signal thresholds** (same as the sample sheet):

| Signal | Strong | Stable | Weak / Watch |
|---|---|---|---|
| Revenue momentum (quarter sales YoY) | ≥ 8% | ≥ 0% | < 0% |
| Profit momentum (quarter net profit YoY) | ≥ 10% | ≥ 0% | < 0% |
| Margin (TTM OPM) | ≥ 42% | ≥ 30% | below |
| ROE | ≥ 15% | ≥ 12% | below |
| Valuation (P/E) | ≤ 15 Attractive | ≤ 20 Normal | > 20 Rich |
| Cash generation | operating cash flow > 0 Positive | | otherwise Weak |

**Overall signal:** 3 or more Weak/Watch → Watch; 4 or more good → Positive; none bad → Neutral-Positive; otherwise Neutral.

**Scenario model** (`calculations/scenario.py`):
- Year+1 sales = TTM sales × (1 + sales growth)
- Year+1 net profit = TTM net profit × (1 + profit growth)
- EPS = net profit / shares
- Implied price = EPS × target P/E
- Upside = implied price / current price − 1

Multi-year outlook compounds the base growth rates.

**Default assumptions are derived from the company's own history, not from the market:**
- base growth = 3-year CAGR of sales / net profit, clipped to 2–20% (sales) and 3–25% (profit)
- bear = 50% and bull = 150% of base growth
- target P/E = current P/E × 0.85 / 1.0 / 1.2

They are editable cells in the Excel (yellow) and the report recalculates. The result is a scenario table, not a price prediction. Confidence starts at 50 (Medium) and rises 4 points per company-specific input you fill in, up to 90.

---

## 6. Generic document analysis (no LLM)

For non-Screener documents (`app/services/document_stats.py`):
- parse markdown tables, then per row compute first / latest / min / max / mean / % change
- pick key figure lines (lines with words like sales, profit, debt plus a number)
- top 15 frequent terms (stop-words removed)

---

## What is and is not an LLM

| Step | LLM? |
|---|---|
| Indicators, rules, scores, conviction, verdict, action | No |
| Statistics, forecast, ratios, scenarios, prediction report | No |
| Document metrics and key lines | No |
| Narrative text (technical, fundamental, RAG summary, risk critique, thesis) | Yes, optional. Falls back to a placeholder sentence when no `OPENAI_API_KEY` is set |
| Embeddings | Optional (`local` works offline) |

## Limits worth knowing

- Forecasts are trend extrapolations. They do not know about the economy, news, or company events.
- Short histories (10 annual points) give wide confidence intervals; the code refuses to fit below 4.
- The technical and fundamental scores use fixed thresholds (for example P/E 15 and 40), which suit some sectors and not others. Lenders, for example, look "Weak" on operating cash flow.
- Not investment advice.

---

## 7. Charts and prediction exports

| Where | What | Endpoint |
|---|---|---|
| Web: Analysis tab, part 2 "Graph & prediction"; app: Analyze tab, part 2 | Candlestick or line chart of the last 60/120/250 daily bars, volume strip, 20-bar moving average | `GET /market/tickers`, `GET /market/ohlcv/{ticker}?limit=` |
| Same chart, "forecast" switch | The next 20 trading days as a dashed line with a shaded 95% interval. Method: the statistics engine's ETS (Holt-Winters, additive trend) over daily closes, ARIMA(1,1,1) when selected. A trend extrapolation, not a market prediction | `GET /market/forecast/{ticker}?history=&ahead=` |
| "Prediction HTML" / "Prediction Excel" buttons | HTML page with a matplotlib chart plus summary and forecast tables; Excel with the actual, forecast and interval columns and a native line chart | `GET /market/forecast/{ticker}/html`, `.../excel` |
| Prediction report for a Screener workbook (Uploads, "Analyze document") | HTML: two graphs (sales and net profit history with the base-case projection, and implied price by scenario against the current price). Excel: the same three as native charts on the Prediction Report sheet, fed by a "chart data" block that follows the scenario cells | `GET /reports/{id}/html`, `GET /reports/{id}/excel` |

The two download links are opened by a browser or phone, which cannot send an `Authorization` header, so they also accept the login token as `?access_token=`. That puts the token in the URL (and in server logs), which is acceptable on a local network but not for a public deployment; put the API behind HTTPS and shorten the token lifetime there.
