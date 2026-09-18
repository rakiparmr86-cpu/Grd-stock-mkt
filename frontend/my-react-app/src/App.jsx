import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import './App.css'
import AuthForm from './AuthForm'
import { API_BASE, getToken, logout, me } from './api'
import { GlobalLoader, TaskActivityProvider } from './taskActivity'

// Each tab is its own chunk, loaded on demand — the tabs are mutually
// exclusive (only one renders at a time), so there's no reason to ship all
// of them in the initial bundle.
const Analysis = lazy(() => import('./Analysis'))
const Inputs = lazy(() => import('./Inputs'))
const Uploads = lazy(() => import('./Uploads'))
const Activity = lazy(() => import('./Activity'))
const Exceptions = lazy(() => import('./Exceptions'))
const Health = lazy(() => import('./Health'))

const TABS = [
  { key: 'analysis', label: 'Analysis', Component: Analysis },
  { key: 'inputs', label: 'Inputs', Component: Inputs },
  { key: 'uploads', label: 'Uploads', Component: Uploads },
  { key: 'activity', label: 'Activity', Component: Activity },
  { key: 'exceptions', label: 'Exceptions', Component: Exceptions },
  { key: 'health', label: 'Health', Component: Health },
]

function Console({ user, onSignOut }) {
  const [page, setPage] = useState('analysis')
  const active = TABS.find((t) => t.key === page) ?? TABS[0]
  const ActiveTab = active.Component

  return (
    <TaskActivityProvider>
      <main className="app">
        <header>
          <h1>grd-stk-mkt</h1>
          <span className="api">{API_BASE}</span>
          <GlobalLoader />
          <span className="spacer" />
          <span className="who">{user?.email}</span>
          <button type="button" className="ghost" onClick={onSignOut}>
            Sign out
          </button>
        </header>
        <div className="tabs page-tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              className={page === t.key ? 'on' : ''}
              onClick={() => setPage(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <Suspense fallback={<p className="muted">loading…</p>}>
          <ActiveTab onExpire={onSignOut} />
        </Suspense>

        <footer>
          Scheduled runs still come from Celery Beat + a worker. This page adds
          sign-in, upload / crawl-now, and an analysis results viewer on top.
        </footer>
      </main>
    </TaskActivityProvider>
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
