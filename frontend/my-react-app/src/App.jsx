import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import Analysis from './Analysis'
import AuthForm from './AuthForm'
import { API_BASE, AuthError, api, getToken, logout, me } from './api'

function Result({ value }) {
  if (!value) return null
  return (
    <pre className={`result ${value.error ? 'err' : 'ok'}`}>
      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
    </pre>
  )
}

// Poll interval and give-up threshold for GET /tasks/{task_id}. If a task is
// still PENDING after this many attempts, a worker is almost certainly not
// running to consume the queue — see app/api/v1/tasks.py.
const TASK_POLL_MS = 1500
const TASK_POLL_MAX_ATTEMPTS = 40

// Uploading a file only *queues* the ingest — the response's task_id says
// nothing about whether that ingest actually ran. Poll it to completion so
// the card shows what really happened instead of the enqueue receipt.
function useTaskPolling(onExpire) {
  const [statuses, setStatuses] = useState({})
  const timers = useRef({})
  const attempts = useRef({})

  useEffect(() => () => {
    Object.values(timers.current).forEach(clearTimeout)
  }, [])

  const poll = useCallback(async function pollTask(taskId) {
    attempts.current[taskId] = (attempts.current[taskId] || 0) + 1
    try {
      const status = await api(`/tasks/${taskId}`)
      setStatuses((prev) => ({ ...prev, [taskId]: status }))
      if (!status.ready) {
        if (attempts.current[taskId] >= TASK_POLL_MAX_ATTEMPTS) {
          setStatuses((prev) => ({
            ...prev,
            [taskId]: {
              ...status,
              timedOut: true,
              hint: 'still pending after 60s — a Celery worker is probably not running',
            },
          }))
          return
        }
        timers.current[taskId] = setTimeout(() => pollTask(taskId), TASK_POLL_MS)
      }
    } catch (err) {
      if (err instanceof AuthError) return onExpire()
      setStatuses((prev) => ({
        ...prev,
        [taskId]: { task_id: taskId, status: 'ERROR', ready: true, error: String(err.message || err) },
      }))
    }
  }, [onExpire])

  const track = useCallback((taskId) => {
    if (!taskId) return
    poll(taskId)
  }, [poll])

  const reset = useCallback(() => {
    Object.values(timers.current).forEach(clearTimeout)
    timers.current = {}
    attempts.current = {}
    setStatuses({})
  }, [])

  return { statuses, track, reset }
}

function TaskStatusRow({ label, status }) {
  if (!status) {
    return (
      <div className="task-row">
        <code>{label}</code>: <span className="muted">queued — checking…</span>
      </div>
    )
  }
  const failed = status.status === 'ERROR' || status.successful === false
  return (
    <div className="task-row">
      <code>{label}</code>:{' '}
      <span className={failed ? 'err-text' : status.ready ? 'ok-text' : 'muted'}>
        {status.status}
        {failed && status.error ? ` — ${status.error}` : ''}
        {status.timedOut ? ` (${status.hint})` : ''}
      </span>
    </div>
  )
}

function UploadCard({ onExpire }) {
  const [files, setFiles] = useState(null)
  const [mode, setMode] = useState('ingest_once')
  const [excelMode, setExcelMode] = useState('docs')
  const [rowKind, setRowKind] = useState('ohlcv')
  const [docType, setDocType] = useState('')
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState(null)
  const { statuses, track, reset } = useTaskPolling(onExpire)

  const submit = async (e) => {
    e.preventDefault()
    if (!files?.length) return
    setBusy(true)
    setOut(null)
    reset()
    try {
      const fd = new FormData()
      for (const f of files) fd.append('files', f)
      fd.append('mode', mode)
      fd.append('excel_mode', excelMode)
      fd.append('row_kind', rowKind)
      if (docType) fd.append('doc_type', docType)
      const res = await api('/inputs/upload', { method: 'POST', body: fd })
      setOut(res)
      for (const item of res.items || []) {
        if (item.task_id) track(item.task_id)
      }
    } catch (err) {
      if (err instanceof AuthError) return onExpire()
      setOut({ error: String(err.message || err) })
    } finally {
      setBusy(false)
    }
  }

  const queuedItems = (out?.items || []).filter((item) => item.task_id)

  return (
    <form className="card" onSubmit={submit}>
      <h2>Upload files</h2>
      <p className="hint">CSV / TSV / Excel / PDF / images (png, jpg, tif…)</p>
      <input
        type="file"
        multiple
        onChange={(e) => setFiles([...e.target.files])}
        accept=".csv,.tsv,.xlsx,.xls,.xlsm,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
      />
      <div className="row">
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="ingest_once">ingest once</option>
            <option value="save_source">save as source</option>
          </select>
        </label>
        <label>
          Excel as
          <select value={excelMode} onChange={(e) => setExcelMode(e.target.value)}>
            <option value="docs">documents</option>
            <option value="rows">price/fundamental rows</option>
          </select>
        </label>
        <label>
          Row kind
          <select value={rowKind} onChange={(e) => setRowKind(e.target.value)}>
            <option value="ohlcv">ohlcv</option>
            <option value="fundamental">fundamental</option>
          </select>
        </label>
        <label>
          doc_type
          <input
            type="text"
            placeholder="(auto)"
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
          />
        </label>
      </div>
      <button disabled={busy || !files?.length}>{busy ? 'Uploading…' : 'Upload'}</button>
      <Result value={out} />
      {queuedItems.length > 0 && (
        <div className="task-status">
          {queuedItems.map((item) => (
            <TaskStatusRow key={item.task_id} label={item.filename} status={statuses[item.task_id]} />
          ))}
        </div>
      )}
    </form>
  )
}

function CrawlCard({ onExpire }) {
  const [url, setUrl] = useState('')
  const [maxDepth, setMaxDepth] = useState(1)
  const [maxPages, setMaxPages] = useState(25)
  const [sameDomain, setSameDomain] = useState(true)
  const [include, setInclude] = useState('')
  const [saveAs, setSaveAs] = useState('')
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true)
    setOut(null)
    try {
      const body = {
        urls: [url.trim()],
        max_depth: Number(maxDepth),
        max_pages: Number(maxPages),
        same_domain_only: sameDomain,
        include_patterns: include.trim() ? [include.trim()] : [],
      }
      if (saveAs.trim()) body.save_as = saveAs.trim()
      setOut(await api('/inputs/crawl', { method: 'POST', body: JSON.stringify(body) }))
    } catch (err) {
      if (err instanceof AuthError) return onExpire()
      setOut({ error: String(err.message || err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Crawl a URL</h2>
      <p className="hint">
        Pages go into the document library. Login-gated sites need an <code>auth</code> block
        (env-var names) — see DATA_FORMATS.md.
      </p>
      <input
        type="url"
        required
        placeholder="https://example.com/reports"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <div className="row">
        <label>
          Depth
          <input
            type="number"
            min="0"
            max="5"
            value={maxDepth}
            onChange={(e) => setMaxDepth(e.target.value)}
          />
        </label>
        <label>
          Max pages
          <input
            type="number"
            min="1"
            max="500"
            value={maxPages}
            onChange={(e) => setMaxPages(e.target.value)}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={sameDomain}
            onChange={(e) => setSameDomain(e.target.checked)}
          />
          same domain only
        </label>
      </div>
      <div className="row">
        <label>
          Include pattern (regex)
          <input
            type="text"
            placeholder="/reports/"
            value={include}
            onChange={(e) => setInclude(e.target.value)}
          />
        </label>
        <label>
          Save as source (optional)
          <input
            type="text"
            placeholder="name — blank = one-off"
            value={saveAs}
            onChange={(e) => setSaveAs(e.target.value)}
          />
        </label>
      </div>
      <button disabled={busy || !url.trim()}>{busy ? 'Queuing…' : 'Start crawl'}</button>
      <Result value={out} />
    </form>
  )
}

// Cell shown in the "Last status" column while a Run click's task is still
// in flight for that row — swaps back to the source's own last_status once
// load() re-fetches after the task completes.
function RunStatusCell({ row, taskStatus }) {
  if (!taskStatus) {
    return (
      <span className={row.last_status === 'error' ? 'err-text' : ''}>
        {row.last_status || '—'}
      </span>
    )
  }
  const failed = taskStatus.status === 'ERROR' || taskStatus.successful === false
  if (failed) {
    return <span className="err-text">failed{taskStatus.error ? ` — ${taskStatus.error}` : ''}</span>
  }
  if (taskStatus.timedOut) {
    return <span className="err-text">{taskStatus.hint}</span>
  }
  if (!taskStatus.ready) {
    return <span className="muted">{taskStatus.status.toLowerCase()}…</span>
  }
  return <span className="ok-text">done — refreshing…</span>
}

function Sources({ onExpire }) {
  const [rows, setRows] = useState([])
  const [err, setErr] = useState(null)
  // sourceId -> task_id, for runs currently in flight from this table
  const [runningTasks, setRunningTasks] = useState({})
  const { statuses, track, reset: resetTasks } = useTaskPolling(onExpire)

  const load = useCallback(async () => {
    try {
      setRows(await api('/inputs'))
      setErr(null)
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setErr(String(e.message || e))
    }
  }, [onExpire])

  useEffect(() => {
    load()
  }, [load])

  // once a tracked task finishes, drop it and pull the row's fresh last_status
  useEffect(() => {
    const done = Object.entries(runningTasks).filter(
      ([, taskId]) => statuses[taskId]?.ready || statuses[taskId]?.timedOut,
    )
    if (done.length === 0) return
    setRunningTasks((prev) => {
      const next = { ...prev }
      for (const [sourceId] of done) delete next[sourceId]
      return next
    })
    load()
  }, [statuses, runningTasks, load])

  const run = async (id) => {
    setErr(null)
    try {
      const res = await api(`/inputs/${id}/run`, { method: 'POST' })
      if (res.task_id) {
        setRunningTasks((prev) => ({ ...prev, [id]: res.task_id }))
        track(res.task_id)
      } else {
        setTimeout(load, 300)
      }
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setErr(String(e.message || e))
    }
  }

  const refresh = () => {
    resetTasks()
    setRunningTasks({})
    load()
  }

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>Saved input sources</h2>
        <button type="button" className="ghost" onClick={refresh}>
          Refresh
        </button>
      </div>
      {err && <pre className="result err">{err}</pre>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Connector</th>
              <th>Active</th>
              <th>Cron</th>
              <th>Last status</th>
              <th>Last stats</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan="7" className="muted">
                  none yet — upload a file as a source, or save a crawl
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const taskId = runningTasks[r.id]
              return (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td>
                    <code>{r.connector}</code>
                  </td>
                  <td>{r.is_active ? 'yes' : 'no'}</td>
                  <td>{r.schedule_cron || '—'}</td>
                  <td>
                    <RunStatusCell row={r} taskStatus={taskId ? statuses[taskId] : null} />
                  </td>
                  <td>
                    <code>{r.last_stats ? JSON.stringify(r.last_stats) : '—'}</code>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="ghost"
                      disabled={!!taskId}
                      onClick={() => run(r.id)}
                    >
                      {taskId ? 'Running…' : 'Run'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Console({ user, onSignOut }) {
  const [page, setPage] = useState('analysis')

  return (
    <main className="app">
      <header>
        <h1>grd-stk-mkt</h1>
        <span className="api">{API_BASE}</span>
        <span className="spacer" />
        <span className="who">{user?.email}</span>
        <button type="button" className="ghost" onClick={onSignOut}>
          Sign out
        </button>
      </header>
      <div className="tabs page-tabs">
        <button type="button" className={page === 'analysis' ? 'on' : ''} onClick={() => setPage('analysis')}>
          Analysis
        </button>
        <button type="button" className={page === 'inputs' ? 'on' : ''} onClick={() => setPage('inputs')}>
          Inputs
        </button>
      </div>

      {page === 'analysis' && <Analysis onExpire={onSignOut} />}

      {page === 'inputs' && (
        <>
          <div className="grid">
            <UploadCard onExpire={onSignOut} />
            <CrawlCard onExpire={onSignOut} />
          </div>
          <Sources onExpire={onSignOut} />
        </>
      )}

      <footer>
        Scheduled runs still come from Celery Beat + a worker. This page adds
        sign-in, upload / crawl-now, and an analysis results viewer on top.
      </footer>
    </main>
  )
}

export default function App() {
  const [state, setState] = useState({ status: 'loading', user: null })

  const check = useCallback(async () => {
    if (!getToken()) {
      setState({ status: 'anon', user: null })
      return
    }
    try {
      const user = await me()
      setState({ status: 'authed', user })
    } catch {
      logout()
      setState({ status: 'anon', user: null })
    }
  }, [])

  useEffect(() => {
    check()
  }, [check])

  const signOut = () => {
    logout()
    setState({ status: 'anon', user: null })
  }

  if (state.status === 'loading') {
    return <div className="boot">…</div>
  }
  if (state.status !== 'authed') {
    return <AuthForm onAuthed={check} />
  }
  return <Console user={state.user} onSignOut={signOut} />
}
