// expo-secure-store has no web backing store, so on web we fall back to
// localStorage — same pattern as the existing use-color-scheme.web.ts split.
const KEY = 'grd_token';

export async function getToken(): Promise<string | null> {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export async function setToken(token: string): Promise<void> {
  try {
    window.localStorage.setItem(KEY, token);
  } catch {
    // private browsing / storage disabled — fall through, user re-logs in
  }
}

export async function clearToken(): Promise<void> {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
