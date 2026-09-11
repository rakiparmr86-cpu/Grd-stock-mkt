import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AuthError,
  getRunDecisions,
  getTask,
  listReports,
  listRuns,
  listSignals,
  reportHtmlUrl,
  triggerRun,
} from './api'

function fmtDate(s) {
  if (!s) return '—'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString()
}

function statusClass(status) {
  if (status === 'error') return 'err-text'
  if (status === 'done' || status === 'SUCCESS') return 'ok-text'
  return ''
}

function Json({ value }) {
  const [open, setOpen] = useState(false)
  if (value == null) return <span className="muted">—</span>
  const text = JSON.stringify(value, null, 2)
  if (text.length < 60 && !text.includes('\n')) return <code>{text}</code>
  return (
    <div>
      <button type="button" className="ghost" onClick={() => setOpen(!open)}>
        {open ? 'hide' : 'view'} JSON
      </button>
      {open && <pre className="result ok">{text}</pre>}
    </div>
  )
}

function RunTrigger({ onQueued, onExpire }) {
  const [ticker, setTicker] = useState('')
  const [strategyId, setStrategyId] = useState('')
  const [async_, setAsync] = useState(true)
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!ticker.trim()) return
    setBusy(true)
    setOut(null)
    try {
      const payload = {
        ticker: ticker.trim().toUpperCase(),
        strategy_id: strategyId.trim() ? Number(strategyId) : null,
        async_,
      }
      const res = await triggerRun(payload)
      setOut(res)
      onQueued?.(res)
    } catch (err) {
      if (err instanceof AuthError) return onExpire()
      setOut({ error: String(err.message || err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Run analysis</h2>
      <p className="hint">Kicks off the agent pipeline for one ticker.</p>
      <div className="row">
        <label>
          Ticker
          <input
            type="text"
            required
            placeholder="HDFCBANK"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
          />
        </label>
        <label>
          Strategy id
          <input
            type="number"
            placeholder="(default)"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
          />
        </label>
        <label className="check">
          <input type="checkbox" checked={async_} onChange={(e) => setAsync(e.target.checked)} />
          async (Celery)
        </label>
      </div>
      <button disabled={busy || !ticker.trim()}>{busy ? 'Starting…' : 'Run'}</button>
      {out && (
        <pre className={`result ${out.error ? 'err' : 'ok'}`}>{JSON.stringify(out, null, 2)}</pre>
      )}
    </form>
  )
}

function TaskWatcher({ taskId, onDone }) {
  const [task, setTask] = useState(null)
  const timer = useRef(null)

  useEffect(() => {
    let stopped = false
    const poll = async () => {
      try {
        const t = await getTask(taskId)
        if (stopped) return
        setTask(t)
        if (t.ready) {
          onDone?.()
          return
        }
      } catch {
        if (stopped) return
      }
      timer.current = setTimeout(poll, 1500)
    }
    poll()
    return () => {
      stopped = true
      clearTimeout(timer.current)
    }
  }, [taskId, onDone])

  if (!task) return <p className="hint">watching task {taskId}…</p>
  return (
    <div className="card">
      <h2>Task {taskId}</h2>
      <p className={statusClass(task.status)}>{task.status}</p>
      {task.error && <pre className="result err">{task.error}</pre>}
      {task.ready && task.result && <pre className="result ok">{JSON.stringify(task.result, null, 2)}</pre>}
    </div>
  )
}

function RunDetail({ run, onExpire }) {
  const [signals, setSignals] = useState([])
  const [reports, setReports] = useState([])
  const [decisions, setDecisions] = useState([])
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!run) return
    let cancelled = false
    ;(async () => {
      try {
        const [s, r, d] = await Promise.all([
          listSignals(run.id),
          listReports(run.id),
          getRunDecisions(run.id),
        ])
        if (cancelled) return
        setSignals(s)
        setReports(r)
        setDecisions(d)
        setErr(null)
      } catch (e) {
        if (cancelled) return
        if (e instanceof AuthError) return onExpire()
        setErr(String(e.message || e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [run, onExpire])

  if (!run) return null

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>
          Run #{run.id} — {run.context?.ticker || '—'}
        </h2>
        <span className={statusClass(run.status)}>{run.status}</span>
      </div>
      <p className="hint">
        trigger: {run.trigger} · started {fmtDate(run.started_at)} · finished{' '}
        {fmtDate(run.finished_at)}
      </p>
      {run.error && <pre className="result err">{run.error}</pre>}
      {err && <pre className="result err">{err}</pre>}

      <h3>Reports</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Summary</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {reports.length === 0 && (
              <tr>
                <td colSpan="4" className="muted">
                  none yet
                </td>
              </tr>
            )}
            {reports.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>{r.summary || '—'}</td>
                <td>{fmtDate(r.created_at)}</td>
                <td>
                  {r.html_path && (
                    <a className="ghost-link" href={reportHtmlUrl(r.id)} target="_blank" rel="noreferrer">
                      View HTML
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Signals</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Strength</th>
              <th>Price</th>
              <th>Triggered</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {signals.length === 0 && (
              <tr>
                <td colSpan="5" className="muted">
                  none yet
                </td>
              </tr>
            )}
            {signals.map((s) => (
              <tr key={s.id}>
                <td>{s.signal_type}</td>
                <td>{s.strength}</td>
                <td>{s.price ?? '—'}</td>
                <td>{fmtDate(s.triggered_at)}</td>
                <td>
                  <Json value={s.detail} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Agent decisions</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Step</th>
              <th>Rationale</th>
              <th>Latency</th>
              <th>Output</th>
            </tr>
          </thead>
          <tbody>
            {decisions.length === 0 && (
              <tr>
                <td colSpan="5" className="muted">
                  none yet
                </td>
              </tr>
            )}
            {decisions.map((d, i) => (
              <tr key={i}>
                <td>{d.agent}</td>
                <td>{d.step}</td>
                <td>{d.rationale || '—'}</td>
                <td>{d.latency_ms != null ? `${d.latency_ms} ms` : '—'}</td>
                <td>
                  <Json value={d.output} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RunsTable({ runs, selectedId, onSelect, onRefresh }) {
  return (
    <div className="card wide">
      <div className="card-head">
        <h2>Recent runs</h2>
        <button type="button" className="ghost" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Ticker</th>
              <th>Trigger</th>
              <th>Status</th>
              <th>Started</th>
              <th>Finished</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 && (
              <tr>
                <td colSpan="6" className="muted">
                  no runs yet — trigger one above
                </td>
              </tr>
            )}
            {runs.map((r) => (
              <tr
                key={r.id}
                className={`clickable ${r.id === selectedId ? 'selected' : ''}`}
                onClick={() => onSelect(r.id)}
              >
                <td>{r.id}</td>
                <td>{r.context?.ticker || '—'}</td>
                <td>{r.trigger}</td>
                <td className={statusClass(r.status)}>{r.status}</td>
                <td>{fmtDate(r.started_at)}</td>
                <td>{fmtDate(r.finished_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function Analysis({ onExpire }) {
  const [runs, setRuns] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [pendingTask, setPendingTask] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const r = await listRuns()
      setRuns(r)
      setErr(null)
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setErr(String(e.message || e))
    }
  }, [onExpire])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleQueued = (res) => {
    if (res.mode === 'async') {
      setPendingTask(res.task_id)
    } else if (res.mode === 'sync') {
      setPendingTask(null)
      refresh()
      if (res.run_id) setSelectedId(res.run_id)
    }
  }

  const selected = runs.find((r) => r.id === selectedId) || null

  return (
    <>
      <RunTrigger onQueued={handleQueued} onExpire={onExpire} />
      {pendingTask && (
        <TaskWatcher
          taskId={pendingTask}
          onDone={() => {
            setPendingTask(null)
            refresh()
          }}
        />
      )}
      {err && <pre className="result err">{err}</pre>}
      <RunsTable runs={runs} selectedId={selectedId} onSelect={setSelectedId} onRefresh={refresh} />
      <RunDetail run={selected} onExpire={onExpire} />
    </>
  )
}
