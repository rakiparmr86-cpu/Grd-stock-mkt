import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { healthServices } from './api'
import { useRefreshButton } from './useRefreshButton'

const POLL_MS = 10000

const LABELS = {
  postgres: 'Postgres',
  redis: 'Redis',
  qdrant: 'Qdrant',
  celery_worker: 'Celery worker',
  celery_beat: 'Celery beat',
}

const ORDER = ['postgres', 'redis', 'qdrant', 'celery_worker', 'celery_beat']

function statusClass(status) {
  if (status === 'up') return 'ok-text'
  if (status === 'down') return 'err-text'
  return 'muted'
}

function StatusBadge({ status }) {
  return <span className={`badge ${status === 'up' ? 'buy' : status === 'down' ? 'sell' : ''}`}>{status}</span>
}

// No auth required — this hits the same unauthenticated /health/* family
// used for infra readiness probes, just with a richer per-service breakdown
// for a human to look at instead of one collapsed ok/degraded verdict.
export default function Health() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [lastChecked, setLastChecked] = useState(null)
  const [openKey, setOpenKey] = useState(null)
  const timer = useRef(null)

  const load = useCallback(async () => {
    try {
      const res = await healthServices()
      setData(res)
      setLastChecked(new Date())
      setErr(null)
    } catch (e) {
      setErr(String(e.message || e))
    }
  }, [])

  const { refreshing, handleClick: handleRefreshClick } = useRefreshButton(load)

  useEffect(() => {
    load()
    timer.current = setInterval(load, POLL_MS)
    return () => clearInterval(timer.current)
  }, [load])

  const services = data?.services || {}
  const anyDown = ORDER.some((k) => services[k]?.status === 'down')

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>System health</h2>
        <div className="row" style={{ margin: 0, alignItems: 'center' }}>
          {lastChecked && (
            <span className="tiny muted">checked {lastChecked.toLocaleTimeString()}</span>
          )}
          <button type="button" className="ghost" onClick={handleRefreshClick} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
      <p className="hint">
        Postgres, Redis, Qdrant, and whether a Celery worker is actually listening — the four
        things that silently going down has repeatedly broken uploads/analysis in this project.
        Auto-refreshes every {POLL_MS / 1000}s. Celery Beat has no equivalent of a worker's ping
        (it only publishes on a schedule, it doesn't respond to anything), so it's always shown
        as "unknown" rather than guessed — check whether a scheduled task's last-run time is
        actually advancing to tell if it's running.
      </p>
      {err && <pre className="result err">{err}</pre>}
      {anyDown && (
        <p className="outcome-note err-text">
          At least one dependency is down — uploads and/or analysis runs will fail until it's
          restarted (usually <code>docker compose up -d postgres redis qdrant mailhog</code>, or
          restarting the Celery worker).
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Service</th>
              <th>Status</th>
              <th>Detail</th>
              <th>Review</th>
            </tr>
          </thead>
          <tbody>
            {!data && !err && (
              <tr>
                <td colSpan="4" className="muted">
                  checking…
                </td>
              </tr>
            )}
            {ORDER.map((key) => {
              const s = services[key]
              if (!s) return null
              const info = s.info && Object.keys(s.info).length ? s.info : null
              const canOpen = Boolean(info || s.hint)
              const isOpen = openKey === key
              return (
                <Fragment key={key}>
                  <tr>
                    <td>{LABELS[key]}</td>
                    <td>
                      <StatusBadge status={s.status} />
                    </td>
                    <td className={statusClass(s.status)}>{s.detail || '—'}</td>
                    <td>
                      <div className="report-links">
                        {s.link && (
                          <a className="ghost-link" href={s.link} target="_blank" rel="noreferrer">
                            Open dashboard ↗
                          </a>
                        )}
                        {canOpen && (
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => setOpenKey(isOpen ? null : key)}
                          >
                            {isOpen ? 'Hide details' : 'View details'}
                          </button>
                        )}
                        {!s.link && !canOpen && <span className="tiny muted">—</span>}
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan="4">
                        {info && (
                          <table>
                            <tbody>
                              {Object.entries(info).map(([k, v]) => (
                                <tr key={k}>
                                  <td className="muted">{k}</td>
                                  <td>{String(v)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                        {s.hint && <p className="tiny muted">{s.hint}</p>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
