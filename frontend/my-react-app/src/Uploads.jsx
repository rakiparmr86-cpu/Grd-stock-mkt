import { useCallback, useEffect, useRef, useState } from 'react'
import { AuthError, uploadsTracker } from './api'

const POLL_MS = 5000

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

// Answers the question every uploader eventually asks: "I uploaded a file —
// did that data ever actually reach an Analysis run?" Ingestion status alone
// (ok/error) only tells you parsing succeeded, not that anyone has since
// clicked Run for that ticker — this closes that loop explicitly per file.
export default function Uploads({ onExpire }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const timer = useRef(null)

  const load = useCallback(async () => {
    try {
      setData(await uploadsTracker(100))
      setErr(null)
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setErr(String(e.message || e))
    }
  }, [onExpire])

  useEffect(() => {
    load()
    timer.current = setInterval(load, POLL_MS)
    return () => clearInterval(timer.current)
  }, [load])

  const items = data?.items || []

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>Uploaded files</h2>
        <button type="button" className="ghost" onClick={load}>
          Refresh
        </button>
      </div>
      <p className="hint">
        Every upload/ingestion, and whether that ticker has actually reached an Analysis run
        since — ingestion succeeding only means the file parsed cleanly, not that anyone has
        run analysis on it yet. Auto-refreshes every {POLL_MS / 1000}s.
      </p>
      {data && (
        <p className="tiny">
          <strong>{data.total}</strong> file{data.total === 1 ? '' : 's'} tracked —{' '}
          <span className="ok-text">{data.analyzed} analyzed</span>,{' '}
          <span className="muted">{data.pending} not yet analyzed</span>
        </p>
      )}
      {err && <pre className="result err">{err}</pre>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>File / source</th>
              <th>Ticker</th>
              <th>Status</th>
              <th>Stats</th>
              <th>Analyzed?</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan="6" className="muted">
                  no uploads yet
                </td>
              </tr>
            )}
            {items.map((it) => (
              <tr key={it.id}>
                <td>{fmtTime(it.finished_at || it.started_at)}</td>
                <td>{it.source_name}</td>
                <td>{it.ticker || '—'}</td>
                <td className={it.status === 'error' ? 'err-text' : it.status === 'ok' ? 'ok-text' : 'muted'}>
                  {it.finished_at ? it.status : 'running…'}
                </td>
                <td>
                  <code>{it.stats && Object.keys(it.stats).length ? JSON.stringify(it.stats) : '—'}</code>
                  {it.error && <div className="tiny err-text">{it.error}</div>}
                </td>
                <td className={it.analyzed ? 'ok-text' : 'muted'}>{it.analyzed ? 'yes' : 'not yet'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
