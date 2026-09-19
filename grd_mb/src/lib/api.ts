// Talks to the same FastAPI backend as frontend/my-react-app. Override the
// default with EXPO_PUBLIC_API_BASE (e.g. in a .env.local file) if none of
// this guesses right for your setup.
import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { clearToken, getToken, setToken } from '@/lib/token-storage';

function defaultApiBase(): string {
  // A physical phone running this through Expo Go/dev client can't reach
  // "localhost" — that's the phone itself, not your dev machine. Metro's own
  // dev server address (host:port, e.g. "192.168.1.5:8081") is exposed here
  // and is already the LAN IP a real device used to load this app, so reuse
  // its host for the API too (same machine, different port).
  const hostUri = Constants.expoConfig?.hostUri;
  const lanHost = hostUri?.split(':')[0];
  if (lanHost && lanHost !== 'localhost' && lanHost !== '127.0.0.1') {
    return `http://${lanHost}:8000/api/v1`;
  }
  // No LAN host available (e.g. web, or a simulator with no hostUri) — fall
  // back to the platform default. Android emulator can't resolve the host
  // machine's "localhost" either; 10.0.2.2 is its documented alias for that.
  const host = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
  return `http://${host}:8000/api/v1`;
}

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? defaultApiBase();

export class AuthError extends Error {}

async function parseBody(res: Response) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export async function api(path: string, opts: RequestInit = {}) {
  const headers = new Headers(opts.headers);
  const token = await getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (opts.body && !(opts.body instanceof FormData) && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  } catch {
    throw new Error(`can't reach the API at ${API_BASE} — is it running and on the same network?`);
  }
  const body = await parseBody(res);
  if (res.status === 401) {
    await clearToken();
    throw new AuthError('session expired — please sign in again');
  }
  if (!res.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `HTTP ${res.status}`);
  }
  return body;
}

// ── auth ──────────────────────────────────────────────────────────
export async function login(email: string, password: string) {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password }).toString(),
    });
  } catch {
    throw new Error(`can't reach the API at ${API_BASE} — is it running and on the same network?`);
  }
  const body = await parseBody(res);
  if (!res.ok) {
    throw new Error(body?.detail || `login failed (HTTP ${res.status})`);
  }
  await setToken(body.access_token);
  return body;
}

export function me() {
  return api('/auth/me');
}

export async function logout() {
  await clearToken();
}

// ── analysis ──────────────────────────────────────────────────────
export type RunPayload = {
  ticker: string;
  strategy_id?: number | null;
  async_?: boolean;
  force_agents?: boolean;
};

export function triggerRun(payload: RunPayload) {
  return api('/runs', { method: 'POST', body: JSON.stringify(payload) });
}

export function getTask(taskId: string) {
  return api(`/tasks/${taskId}`);
}

export function listRuns(limit = 30) {
  return api(`/runs?limit=${limit}`);
}

export function getRun(runId: number | string) {
  return api(`/runs/${runId}`);
}

export function listReports(runId: number | string) {
  return api(`/reports?run_id=${runId}&limit=5`);
}

export function getRunDecisions(runId: number | string) {
  return api(`/runs/${runId}/decisions`);
}

export function listSignals(runId: number | string) {
  return api(`/signals?run_id=${runId}&limit=200`);
}

export function listReportsFull(runId: number | string) {
  return api(`/reports?run_id=${runId}&limit=50`);
}

// Same URLs the web frontend links to; open them in the device browser.
export function reportHtmlUrl(reportId: number) {
  return `${API_BASE}/reports/${reportId}/html`;
}

export function reportExcelUrl(reportId: number) {
  return `${API_BASE}/reports/${reportId}/excel`;
}

// ── uploads / document analysis ───────────────────────────────────
export function triggerDocumentRun(ingestionRunId: number, async_ = true) {
  return api('/runs/document', {
    method: 'POST',
    body: JSON.stringify({ ingestion_run_id: ingestionRunId, async_ }),
  });
}

export function uploadsTracker(limit = 100) {
  return api(`/inputs/uploads-tracker?limit=${limit}`);
}

export type UploadOptions = {
  mode: 'ingest_once' | 'save_source';
  excelMode: 'docs' | 'rows';
  rowKind: 'ohlcv' | 'fundamental';
  ticker?: string;
  docType?: string;
};

export type PickedFile = { uri: string; name: string; mimeType?: string | null; file?: File };

export function uploadFiles(files: PickedFile[], opts: UploadOptions) {
  const fd = new FormData();
  for (const f of files) {
    // web gives a real File; native needs the {uri,name,type} shape RN understands
    if (Platform.OS === 'web' && f.file) fd.append('files', f.file, f.name);
    else {
      const part = { uri: f.uri, name: f.name, type: f.mimeType ?? 'application/octet-stream' };
      fd.append('files', part as unknown as Blob);
    }
  }
  fd.append('mode', opts.mode);
  fd.append('excel_mode', opts.excelMode);
  fd.append('row_kind', opts.rowKind);
  if (opts.docType) fd.append('doc_type', opts.docType);
  if (opts.ticker?.trim()) fd.append('ticker', opts.ticker.trim().toUpperCase());
  return api('/inputs/upload', { method: 'POST', body: fd });
}

export function listSources() {
  return api('/inputs');
}

export function runSource(id: number) {
  return api(`/inputs/${id}/run`, { method: 'POST' });
}

// ── system health / activity / exceptions ─────────────────────────
export function healthServices() {
  return api('/health/services');
}

export function listActivity(limit = 150) {
  return api(`/activity?limit=${limit}`);
}

export function listExceptions(limit = 200) {
  return api(`/exceptions?limit=${limit}`);
}

export function deleteException(id: number) {
  return api(`/exceptions/${id}`, { method: 'DELETE' });
}
