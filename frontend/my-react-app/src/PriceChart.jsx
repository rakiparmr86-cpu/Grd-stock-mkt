import { useCallback, useEffect, useMemo, useState } from 'react'
import { AuthError, forecastExportUrl, getForecast, getOhlcv, listPriceTickers } from './api'
import { useRefreshButton } from './useRefreshButton'

const W = 800
const H = 320
const PAD = { l: 56, r: 12, t: 10, b: 24 }
const VOL_H = 46
const PRICE_BOTTOM = H - PAD.b - VOL_H - 6
const RANGES = [60, 120, 250]
const AHEAD = 20

function sma(closes, n) {
  return closes.map((_, i) => {
    if (i < n - 1) return null
    let s = 0
    for (let k = i - n + 1; k <= i; k++) s += closes[k]
    return s / n
  })
}

function fmt(n) {
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'
}

function fmtDay(ts) {
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function Chart({ bars, mode, showSma, forecast }) {
  const [hover, setHover] = useState(null)
  const fc = useMemo(() => forecast || [], [forecast])
  const total = bars.length + fc.length

  const geo = useMemo(() => {
    const lows = [...bars.map((b) => b.low), ...fc.map((f) => f.low)]
    const highs = [...bars.map((b) => b.high), ...fc.map((f) => f.high)]
    let lo = Math.min(...lows)
    let hi = Math.max(...highs)
    const pad = (hi - lo) * 0.06 || 1
    lo -= pad
    hi += pad
    const plotW = W - PAD.l - PAD.r
    const step = plotW / total
    const y = (v) => PAD.t + ((hi - v) / (hi - lo)) * (PRICE_BOTTOM - PAD.t)
    const x = (i) => PAD.l + step * i + step / 2
    const maxVol = Math.max(...bars.map((b) => b.volume), 1)
    return { lo, hi, step, x, y, maxVol }
  }, [bars, fc, total])

  const closes = useMemo(() => bars.map((b) => b.close), [bars])
  const sma20 = useMemo(() => sma(closes, 20), [closes])

  const yTicks = Array.from({ length: 5 }, (_, i) => geo.lo + ((geo.hi - geo.lo) * i) / 4)
  const allTs = [...bars.map((b) => b.ts), ...fc.map((f) => f.ts)]
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.min(total - 1, Math.round(f * (total - 1))))
  const candleW = Math.max(1, geo.step * 0.62)

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    const idx = Math.floor((px - PAD.l) / geo.step)
    setHover(idx >= 0 && idx < total ? idx : null)
  }

  const last = bars[bars.length - 1]
  const hoverFc = hover != null && hover >= bars.length ? fc[hover - bars.length] : null
  const shown = hover != null && !hoverFc ? bars[hover] : last
  const prev = hover != null && !hoverFc ? bars[hover - 1] : bars[bars.length - 2]
  const change = prev ? ((shown.close - prev.close) / prev.close) * 100 : null

  const linePts = bars.map((b, i) => `${geo.x(i)},${geo.y(b.close)}`).join(' ')
  const smaPts = sma20
    .map((v, i) => (v == null ? null : `${geo.x(i)},${geo.y(v)}`))
    .filter(Boolean)
    .join(' ')

  return (
    <div>
      {hoverFc ? (
        <p className="tiny" style={{ margin: '0 0 6px' }}>
          <strong>{fmtDay(hoverFc.ts)}</strong> &nbsp; forecast {fmt(hoverFc.value)} &nbsp; (95%: {fmt(hoverFc.low)} – {fmt(hoverFc.high)})
        </p>
      ) : (
      <p className="tiny" style={{ margin: '0 0 6px' }}>
        <strong>{fmtDay(shown.ts)}</strong> &nbsp; O {fmt(shown.open)} &nbsp; H {fmt(shown.high)} &nbsp; L{' '}
        {fmt(shown.low)} &nbsp; C {fmt(shown.close)}
        {change != null && (
          <span className={change >= 0 ? 'ok-text' : 'err-text'}>
            {' '}
            &nbsp; {change >= 0 ? '+' : ''}
            {change.toFixed(2)}%
          </span>
        )}
      </p>
      )}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', height: 'auto', display: 'block' }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="price chart"
      >
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={geo.y(t)} y2={geo.y(t)} stroke="currentColor" opacity="0.12" />
            <text x={PAD.l - 6} y={geo.y(t) + 4} textAnchor="end" fontSize="11" fill="currentColor" opacity="0.6">
              {fmt(t)}
            </text>
          </g>
        ))}
        {xTicks.map((i) => (
          <text key={i} x={geo.x(i)} y={H - 6} textAnchor="middle" fontSize="11" fill="currentColor" opacity="0.6">
            {fmtDay(allTs[i])}
          </text>
        ))}

        {bars.map((b, i) => (
          <rect
            key={`v${i}`}
            x={geo.x(i) - candleW / 2}
            width={candleW}
            y={H - PAD.b - (b.volume / geo.maxVol) * VOL_H}
            height={(b.volume / geo.maxVol) * VOL_H}
            fill={b.close >= b.open ? '#1a7f37' : '#b42318'}
            opacity="0.35"
          />
        ))}

        {mode === 'line' ? (
          <>
            <polygon
              points={`${geo.x(0)},${PRICE_BOTTOM} ${linePts} ${geo.x(bars.length - 1)},${PRICE_BOTTOM}`}
              fill="#2563eb"
              opacity="0.12"
            />
            <polyline points={linePts} fill="none" stroke="#2563eb" strokeWidth="2" />
          </>
        ) : (
          bars.map((b, i) => {
            const up = b.close >= b.open
            const color = up ? '#1a7f37' : '#b42318'
            const top = geo.y(Math.max(b.open, b.close))
            const bodyH = Math.max(1, Math.abs(geo.y(b.open) - geo.y(b.close)))
            return (
              <g key={i}>
                <line x1={geo.x(i)} x2={geo.x(i)} y1={geo.y(b.high)} y2={geo.y(b.low)} stroke={color} strokeWidth="1" />
                <rect x={geo.x(i) - candleW / 2} y={top} width={candleW} height={bodyH} fill={color} />
              </g>
            )
          })
        )}

        {fc.length > 0 && (
          <>
            <polygon
              points={[
                ...fc.map((f, j) => `${geo.x(bars.length + j)},${geo.y(f.high)}`),
                ...[...fc].reverse().map((f, j) => `${geo.x(total - 1 - j)},${geo.y(f.low)}`),
              ].join(' ')}
              fill="#d97706"
              opacity="0.18"
            />
            <polyline
              points={[
                `${geo.x(bars.length - 1)},${geo.y(last.close)}`,
                ...fc.map((f, j) => `${geo.x(bars.length + j)},${geo.y(f.value)}`),
              ].join(' ')}
              fill="none"
              stroke="#d97706"
              strokeWidth="2"
              strokeDasharray="6 4"
            />
            <line
              x1={geo.x(bars.length - 1) + geo.step / 2}
              x2={geo.x(bars.length - 1) + geo.step / 2}
              y1={PAD.t}
              y2={PRICE_BOTTOM}
              stroke="currentColor"
              opacity="0.25"
            />
          </>
        )}

        {showSma && smaPts && <polyline points={smaPts} fill="none" stroke="#7c3aed" strokeWidth="1.5" />}

        {hover != null && (
          <line
            x1={geo.x(hover)}
            x2={geo.x(hover)}
            y1={PAD.t}
            y2={H - PAD.b}
            stroke="currentColor"
            opacity="0.4"
            strokeDasharray="3 3"
          />
        )}
      </svg>
    </div>
  )
}

// Small price chart for presentations: candles or a line, with an optional
// 20-bar moving average and a volume strip. Data comes from the same OHLCV
// table the technical analysis reads, via GET /market/ohlcv/{ticker}.
export default function PriceChart({ onExpire }) {
  const [tickers, setTickers] = useState([])
  const [ticker, setTicker] = useState('')
  const [limit, setLimit] = useState(120)
  const [mode, setMode] = useState('candles')
  const [showSma, setShowSma] = useState(true)
  const [showForecast, setShowForecast] = useState(true)
  const [bars, setBars] = useState([])
  const [forecast, setForecast] = useState(null)
  const [fcNote, setFcNote] = useState(null)
  const [err, setErr] = useState(null)

  const loadTickers = useCallback(async () => {
    try {
      const list = await listPriceTickers()
      setTickers(list)
      setTicker((cur) => cur || list[0]?.ticker || '')
      setErr(null)
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setErr(String(e.message || e))
    }
  }, [onExpire])

  const loadBars = useCallback(async () => {
    if (!ticker) return
    try {
      const res = await getOhlcv(ticker, limit)
      setBars(res.bars)
      setErr(null)
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setBars([])
      setErr(String(e.message || e))
    }
  }, [ticker, limit, onExpire])

  const loadForecast = useCallback(async () => {
    if (!ticker || !showForecast) {
      setForecast(null)
      setFcNote(null)
      return
    }
    try {
      const res = await getForecast(ticker, limit, AHEAD)
      setForecast(res)
      setFcNote(null)
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setForecast(null)
      setFcNote(String(e.message || e))
    }
  }, [ticker, limit, showForecast, onExpire])

  const reloadAll = useCallback(async () => {
    await loadTickers()
    await loadBars()
    await loadForecast()
  }, [loadTickers, loadBars, loadForecast])

  const { refreshing, handleClick: handleRefreshClick } = useRefreshButton(reloadAll)

  useEffect(() => {
    loadTickers()
  }, [loadTickers])

  useEffect(() => {
    loadBars()
  }, [loadBars])

  useEffect(() => {
    loadForecast()
  }, [loadForecast])

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>Price chart</h2>
        <button type="button" className="ghost" onClick={handleRefreshClick} disabled={refreshing}>
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      {tickers.length === 0 && !err ? (
        <p className="hint">
          No price data yet — upload a price CSV (or Excel as rows, row kind &quot;ohlcv&quot;) in the Inputs
          tab and it will show here.
        </p>
      ) : (
        <>
          <div className="row" style={{ alignItems: 'center' }}>
            <label>
              Ticker
              <select value={ticker} onChange={(e) => setTicker(e.target.value)}>
                {tickers.map((t) => (
                  <option key={t.ticker} value={t.ticker}>
                    {t.ticker} ({t.bars} bars)
                  </option>
                ))}
              </select>
            </label>
            <label>
              Bars
              <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                {RANGES.map((r) => (
                  <option key={r} value={r}>
                    last {r}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Style
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="candles">candlesticks</option>
                <option value="line">line</option>
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={showSma} onChange={(e) => setShowSma(e.target.checked)} />
              20-bar average
            </label>
            <label className="check">
              <input type="checkbox" checked={showForecast} onChange={(e) => setShowForecast(e.target.checked)} />
              show {AHEAD}-day forecast
            </label>
          </div>
          {err && <pre className="result err">{err}</pre>}
          {bars.length > 0 && (
            <Chart bars={bars} mode={mode} showSma={showSma} forecast={forecast?.forecast} />
          )}
          {fcNote && <p className="hint">Forecast not shown: {fcNote}</p>}
          {forecast && (
            <p className="hint">
              {forecast.method.toUpperCase()} forecast: {fmt(forecast.last_close)} →{' '}
              {fmt(forecast.forecast_end)} in {forecast.ahead} bars (
              {forecast.forecast_change_pct >= 0 ? '+' : ''}
              {forecast.forecast_change_pct?.toFixed(1)}%), 95% interval shaded. A trend
              extrapolation, not advice.
            </p>
          )}
          {ticker && (
            <div className="report-links">
              <a className="ghost-link" href={forecastExportUrl(ticker, 'html', limit, AHEAD)} target="_blank" rel="noreferrer">
                Prediction HTML ↗
              </a>
              <a className="ghost-link" href={forecastExportUrl(ticker, 'excel', limit, AHEAD)}>
                Prediction Excel ↓
              </a>
            </div>
          )}
        </>
      )}
    </div>
  )
}
