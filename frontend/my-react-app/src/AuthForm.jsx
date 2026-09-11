import { useState } from 'react'
import { login, register } from './api'

export default function AuthForm({ onAuthed }) {
  const [tab, setTab] = useState('login') // 'login' | 'register'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [note, setNote] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    setNote(null)
    try {
      if (tab === 'register') {
        await register(email.trim(), password, fullName.trim())
        setNote('Account created — signing you in…')
      }
      await login(email.trim(), password)
      onAuthed()
    } catch (e2) {
      setErr(String(e2.message || e2))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth" onSubmit={submit}>
        <h1></h1>
        <div className="tabs">
          <button
            type="button"
            className={tab === 'login' ? 'on' : ''}
            onClick={() => setTab('login')}
          >
            Sign in
          </button>
          <button
            type="button"
            className={tab === 'register' ? 'on' : ''}
            onClick={() => setTab('register')}
          >
            Create account
          </button>
        </div>

        {tab === 'register' && (
          <label>
            Name
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="optional"
            />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            minLength={tab === 'register' ? 8 : undefined}
            autoComplete={tab === 'register' ? 'new-password' : 'current-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {tab === 'register' && <span className="tiny">at least 8 characters</span>}
        </label>

        <button disabled={busy}>
          {busy ? '…' : tab === 'register' ? 'Create account & sign in' : 'Sign in'}
        </button>
        {note && <pre className="result ok">{note}</pre>}
        {err && <pre className="result err">{err}</pre>}
      </form>
    </div>
  )
}
