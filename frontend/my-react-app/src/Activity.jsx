import { useCallback, useEffect, useRef, useState } from 'react'
import { AuthError, listActivity } from './api'

const POLL_MS = 5000

const TYPE_LABELS = {
  run_started: 'Run started',
  run_finished: 'Run finished',
  agent_decision: 'Agent decision',
  signal: 'Signal',
  report: 'Report',
  alert: 'Alert',
  ingestion_started: 'Ingest started',
  ingestion_finished: 'Ingest finished',
}

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function statusClass(status) {
  if (['error', 'failed', 'sell'].includes(status)) return 'err-text'
  if (['done', 'ok', 'buy', 'sent'].includes(status)) return 'ok-text'
  return 'muted'
}

export default function Activity({ onExpire }) {
  const [events, setEvents] = useState([])
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)
  const [paused, setPaused] = useState(false)
  const timer = useRef(null)

  const load = useCallback(async () => {
    try {
      const rows = await listActivity(150)
      setEvents(rows)
      setErr(null)
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setErr(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }, [onExpire])

  useEffect(() => {
    load()
    if (paused) return undefined
    timer.current = setInterval(load, POLL_MS)
    return () => clearInterval(timer.current)
  }, [load, paused])

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>Activity</h2>
        <div className="row" style={{ margin: 0, alignItems: 'center' }}>
          <span className="tiny">
            {paused ? 'auto-refresh paused' : `auto-refreshing every ${POLL_MS / 1000}s`}
          </span>
          <button type="button" className="ghost" onClick={() => setPaused((p) => !p)}>
            {paused ? 'Resume' : 'Pause'}
          </button>
          <button type="button" className="ghost" onClick={load}>
            Refresh now
          </button>
        </div>
      </div>
      <p className="hint">
        A merged, time-sorted feed of everything happening across the project — analysis runs,
        individual agent decisions inside each run, triggered signals, generated reports, sent
        alerts, and input-source ingestions. Polled every {POLL_MS / 1000}s, not push-based.
      </p>
      {err && <pre className="result err">{err}</pre>}
      {loading && !events.length ? (
        <p className="muted">loading…</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Ticker</th>
                <th>What happened</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 && (
                <tr>
                  <td colSpan="5" className="muted">
                    no activity yet
                  </td>
                </tr>
              )}
              {events.map((e) => (
                <tr key={e.id}>
                  <td>{fmtTime(e.at)}</td>
                  <td>{TYPE_LABELS[e.type] || e.type}</td>
                  <td>{e.ticker || '—'}</td>
                  <td>
                    <strong>{e.title}</strong>
                    {e.detail && <div className="tiny">{e.detail}</div>}
                  </td>
                  <td className={statusClass(e.status)}>{e.status || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
