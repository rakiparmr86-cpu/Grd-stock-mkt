import { useCallback, useEffect, useState } from 'react'
import './App.css'

const API = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts)
  const text = await res.text()
  let body
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!res.ok) {
    const msg = body?.detail ? JSON.stringify(body.detail) : `HTTP ${res.status}`
    throw new Error(msg)
  }
  return body
}

function Result({ value }) {
  if (!value) return null
  return (
    <pre className={`result ${value.error ? 'err' : 'ok'}`}>
      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
    </pre>
  )
}

function UploadCard() {
  const [files, setFiles] = useState(null)
  const [mode, setMode] = useState('ingest_once')
  const [excelMode, setExcelMode] = useState('docs')
  const [rowKind, setRowKind] = useState('ohlcv')
  const [docType, setDocType] = useState('')
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!files?.length) return
    setBusy(true)
    setOut(null)
    try {
      const fd = new FormData()
      for (const f of files) fd.append('files', f)
      fd.append('mode', mode)
      fd.append('excel_mode', excelMode)
      fd.append('row_kind', rowKind)
      if (docType) fd.append('doc_type', docType)
      setOut(await api('/inputs/upload', { method: 'POST', body: fd }))
    } catch (err) {
      setOut({ error: String(err.message || err) })
    } finally {
      setBusy(false)
    }
  }

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
    </form>
  )
}

function CrawlCard() {
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
      setOut(
        await api('/inputs/crawl', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(body),
        }),
      )
    } catch (err) {
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

function Sources() {
  const [rows, setRows] = useState([])
  const [err, setErr] = useState(null)

  const load = useCallback(async () => {
    try {
      setRows(await api('/inputs'))
      setErr(null)
    } catch (e) {
      setErr(String(e.message || e))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const run = async (id) => {
    try {
      await api(`/inputs/${id}/run`, { method: 'POST' })
      setTimeout(load, 800)
    } catch (e) {
      setErr(String(e.message || e))
    }
  }

  return (
    <div className="card wide">
      <div className="card-head">
        <h2>Saved input sources</h2>
        <button type="button" className="ghost" onClick={load}>
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
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>
                  <code>{r.connector}</code>
                </td>
                <td>{r.is_active ? 'yes' : 'no'}</td>
                <td>{r.schedule_cron || '—'}</td>
                <td className={r.last_status === 'error' ? 'err-text' : ''}>
                  {r.last_status || '—'}
                </td>
                <td>
                  <code>{r.last_stats ? JSON.stringify(r.last_stats) : '—'}</code>
                </td>
                <td>
                  <button type="button" className="ghost" onClick={() => run(r.id)}>
                    Run
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <main className="app">
      <header>
        <h1>grd-stk-mkt — inputs</h1>
        <span className="api">{API}</span>
      </header>
      <div className="grid">
        <UploadCard />
        <CrawlCard />
      </div>
      <Sources />
      <footer>
        Scheduled runs still come from Celery Beat + a worker. This page just adds
        upload / crawl-now on top.
      </footer>
    </main>
  )
}
