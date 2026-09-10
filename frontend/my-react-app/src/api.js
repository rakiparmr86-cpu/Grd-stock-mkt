// Tiny API client: base URL, bearer-token storage, and a fetch wrapper that
// attaches the token and normalises errors (401 -> AuthError).

export const API_BASE =
  import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'

const TOKEN_KEY = 'grd_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}
export function setToken(t) {
  try {
    localStorage.setItem(TOKEN_KEY, t)
  } catch {
    /* private mode — token lives only in memory for this tab */
  }
}
export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

export class AuthError extends Error {}

async function parse(res) {
  const text = await res.text()
  try {
    return text ? JSON.parse(text) : null
  } catch {
    return text
  }
}

// api('/inputs', { method, headers, body })  — JSON in/out by default.
// Pass a FormData body and the content-type is left to the browser.
export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (opts.body && !(opts.body instanceof FormData) && !headers['content-type']) {
    headers['content-type'] = 'application/json'
  }

  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers })
  const body = await parse(res)
  if (res.status === 401) {
    clearToken()
    throw new AuthError('session expired — please sign in again')
  }
  if (!res.ok) {
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `HTTP ${res.status}`)
  }
  return body
}

// ── auth calls ────────────────────────────────────────────────────
export async function login(email, password) {
  // OAuth2 password flow → form-encoded, field name is "username"
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  })
  const body = await parse(res)
  if (!res.ok) {
    throw new Error(body?.detail || `login failed (HTTP ${res.status})`)
  }
  setToken(body.access_token)
  return body
}

export async function register(email, password, fullName) {
  return api('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, full_name: fullName || null }),
  })
}

export function me() {
  return api('/auth/me')
}

export function logout() {
  clearToken()
}
