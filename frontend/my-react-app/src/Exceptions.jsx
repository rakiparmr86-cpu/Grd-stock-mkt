import { useCallback, useEffect, useState } from 'react'
import { AuthError, deleteException, listExceptions } from './api'

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function TracebackToggle({ traceback }) {
  const [open, setOpen] = useState(false)
  if (!traceback) return <span className="muted">—</span>
  return (
    <div>
      <button type="button" className="ghost" onClick={() => setOpen(!open)}>
        {open ? 'hide' : 'view'} traceback
      </button>
      {open && <pre className="result err">{traceback}</pre>}
    </div>
  )
}

export default function Exceptions({ onExpire }) {
  const [rows, setRows] = useState([])
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await listExceptions(200)
      setRows(data)
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
  }, [load])

  const handleDelete = async (id) => {
    if (!window.confirm('Permanently delete this exception log entry? This cannot be undone.')) {
      return
    }
    setDeletingId(id)
    try {
      await deleteException(id)
      setRows((prev) => prev.filter((r) => r.id !== id))
    } catch (e) {
      if (e instanceof AuthError) return onExpire()
      setErr(String(e.message || e))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>Exceptions</h2>
        <button type="button" className="ghost" onClick={load}>
          Refresh
        </button>
      </div>
      <p className="hint">
        Unexpected failures from anywhere in the system — unhandled API errors, websocket handler
        errors, and Celery task failures (analysis runs, input-source ingestions). Expected errors
        (a plain 404, a validation error) are not logged here — only genuine bugs. Deleting an
        entry is permanent; there's no undo.
      </p>
      {err && <pre className="result err">{err}</pre>}
      {loading && !rows.length ? (
        <p className="muted">loading…</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Source</th>
                <th>Message</th>
                <th>Context</th>
                <th>Traceback</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan="6" className="muted">
                    no exceptions logged
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{fmtTime(r.created_at)}</td>
                  <td>{r.source}</td>
                  <td>{r.message}</td>
                  <td>
                    <code>{Object.keys(r.context || {}).length ? JSON.stringify(r.context) : '—'}</code>
                  </td>
                  <td>
                    <TracebackToggle traceback={r.traceback} />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="ghost"
                      disabled={deletingId === r.id}
                      onClick={() => handleDelete(r.id)}
                    >
                      {deletingId === r.id ? 'deleting…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
