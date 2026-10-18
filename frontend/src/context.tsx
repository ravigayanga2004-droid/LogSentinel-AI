import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, workspaceId } from './api';
import type { Role, User, Workspace } from './types';

interface AuthValue { user: User; workspace: Workspace; switchWorkspace: (id: string) => void; }
const Auth = createContext<AuthValue | null>(null);
export function useAuth() { const value = useContext(Auth); if (!value) throw new Error('Authentication context unavailable'); return value; }
export function useSession() { return useQuery({ queryKey: ['session'], queryFn: () => api<User>('/auth/me'), retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 1, staleTime: 60000 }); }
export function AuthProvider({ user, children }: { user: User; children: ReactNode }) {
  const [id, setId] = useState(workspaceId);
  const queryClient = useQueryClient();
  const workspace = user.workspaces.find((item) => item.id === id) ?? user.workspaces[0];
  useEffect(() => { if (workspace) localStorage.setItem('ls_workspace', workspace.id); }, [workspace]);
  if (!workspace) return <div className="state-box">Your account has no workspace membership. Contact your administrator.</div>;
  const switchWorkspace = (next: string) => { localStorage.setItem('ls_workspace', next); setId(next); queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'session' }); };
  return <Auth.Provider value={{ user, workspace, switchWorkspace }}>{children}</Auth.Provider>;
}

export function useCan(permission: 'admin' | 'sources' | 'ingest' | 'investigate' | 'rules' | 'export') {
  const { workspace } = useAuth();
  const allowed: Record<Role, string[]> = { administrator: ['admin', 'sources', 'ingest', 'investigate', 'rules', 'export'], analyst: ['ingest', 'investigate', 'rules', 'export'], viewer: [], source_admin: ['sources', 'ingest'] };
  return allowed[workspace.role].includes(permission);
}

type Theme = 'dark' | 'light';
const ThemeContext = createContext({ theme: 'dark' as Theme, toggle: () => {} });
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => localStorage.getItem('ls_theme') === 'light' ? 'light' : 'dark');
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('ls_theme', theme); }, [theme]);
  return <ThemeContext.Provider value={{ theme, toggle: () => setTheme((value) => value === 'dark' ? 'light' : 'dark') }}>{children}</ThemeContext.Provider>;
}
export function useTheme() { return useContext(ThemeContext); }

const ToastContext = createContext<(message: string, error?: boolean) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<{ id: number; message: string; error: boolean }[]>([]);
  function notify(message: string, error = false) { const id = Date.now() + Math.random(); setToasts((current) => [...current.slice(-3), { id, message, error }]); window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), error ? 12000 : 5000); }
  return <ToastContext.Provider value={notify}>{children}<div className="toasts" aria-live="polite">{toasts.map((toast) => <div key={toast.id} className={`toast ${toast.error ? 'error' : ''}`} role={toast.error ? 'alert' : 'status'}><span>{toast.message}</span><button aria-label="Dismiss notification" onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}>×</button></div>)}</div></ToastContext.Provider>;
}
export function useToast() { return useContext(ToastContext); }
export function useAction() {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const queries = useQueryClient();
  async function run<T>(action: () => Promise<T>, message: string): Promise<T | undefined> {
    setBusy(true);
    try { const result = await action(); await queries.invalidateQueries(); toast(message); return result; }
    catch (error) { toast(error instanceof Error ? error.message : 'Something went wrong', true); return undefined; }
    finally { setBusy(false); }
  }
  return { busy, run };
}
