import { createContext, use, useCallback, useEffect, useMemo, useState } from 'react';

import * as api from '@/lib/api';
import { getToken } from '@/lib/token-storage';

type User = { id: number; email: string; full_name: string | null };
type Status = 'loading' | 'anon' | 'authed';

type AuthContextValue = {
  status: Status;
  user: User | null;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>('loading');
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkSession = useCallback(async () => {
    const token = await getToken();
    if (!token) {
      setStatus('anon');
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
      setStatus('authed');
    } catch {
      await api.logout();
      setStatus('anon');
    }
  }, []);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  const signIn = useCallback(async (email: string, password: string) => {
    setError(null);
    try {
      await api.login(email, password);
      const me = await api.me();
      setUser(me);
      setStatus('authed');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  }, []);

  const signOut = useCallback(async () => {
    await api.logout();
    setUser(null);
    setStatus('anon');
  }, []);

  const value = useMemo(
    () => ({ status, user, error, signIn, signOut }),
    [status, user, error, signIn, signOut],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const ctx = use(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
