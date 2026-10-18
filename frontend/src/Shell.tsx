import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Bell,
  BookOpen,
  ChevronRight,
  CircleHelp,
  FileBarChart2,
  Fingerprint,
  LayoutDashboard,
  ListFilter,
  LogOut,
  Menu,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
  X,
} from 'lucide-react';
import { api } from './api';
import { useAction, useAuth, useCan } from './context';
import { Brand, ThemeToggle } from './Public';
import type { Metrics } from './types';

const mainLinks = [
  { path: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { path: '/events', label: 'Events explorer', icon: ListFilter },
  { path: '/alerts', label: 'Alerts', icon: ShieldCheck },
  { path: '/investigations', label: 'Investigations', icon: Fingerprint },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
];
export function Shell() {
  const { user, workspace, switchWorkspace } = useAuth();
  const [menu, setMenu] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const queries = useQueryClient();
  const action = useAction();
  const canAdmin = useCan('admin'),
    canIngest = useCan('ingest'),
    canExport = useCan('export');
  const metrics = useQuery({
    queryKey: ['nav-metrics', workspace.id],
    queryFn: () => api<Metrics>('/analytics?hours=24'),
    refetchInterval: 60000,
  });
  const health = useQuery({
    queryKey: ['readiness'],
    queryFn: async () => {
      const result = await fetch('/api/ready');
      return result.json() as Promise<{ status: string }>;
    },
    refetchInterval: 30000,
  });
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (
        event.key === '/' &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes((event.target as HTMLElement).tagName)
      ) {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === 'Escape') setMenu(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);
  const section =
    [
      ...mainLinks,
      { path: '/sources', label: 'Log sources' },
      { path: '/parsers', label: 'Parser lab' },
      { path: '/rules', label: 'Detection rules' },
      { path: '/reports', label: 'Reports' },
      { path: '/notifications', label: 'Notifications' },
      { path: '/profile', label: 'Your profile' },
      { path: '/security', label: 'Security settings' },
      { path: '/audit', label: 'Audit trail' },
      { path: '/settings', label: 'Administration' },
    ].find((item) => location.pathname.startsWith(item.path))?.label ?? 'Workspace';
  async function logout() {
    const result = await action.run(() => api('/auth/logout', 'POST'), 'You have signed out');
    if (result) {
      queries.clear();
      localStorage.removeItem('ls_workspace');
      navigate('/login');
    }
  }
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    navigate(`/events?q=${encodeURIComponent(String(data.get('q') ?? ''))}`);
  }
  function nav(path: string, label: string, Icon: typeof Activity) {
    return (
      <NavLink
        key={path}
        to={path}
        className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
        onClick={() => setMenu(false)}
      >
        <Icon size={16} strokeWidth={1.7} />
        <span>{label}</span>
        {path === '/alerts' && !!metrics.data?.open_alerts && (
          <span className="nav-count">{metrics.data.open_alerts}</span>
        )}
      </NavLink>
    );
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {menu && (
        <button
          className="sidebar-overlay"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={`sidebar ${menu ? 'open' : ''}`}>
        <Brand />
        <div className="workspace-picker">
          <span className="workspace-mark">{workspace.name.slice(0, 1)}</span>
          <label>
            <small>WORKSPACE</small>
            <select
              aria-label="Current workspace"
              value={workspace.id}
              onChange={(event) => switchWorkspace(event.target.value)}
            >
              {user.workspaces.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <nav aria-label="Main navigation">
          <div className="nav-section-title">MONITOR</div>
          <div className="nav-list">
            {mainLinks.map(({ path, label, icon }) => nav(path, label, icon))}
          </div>
          <div className="nav-section-title" style={{ marginTop: 27 }}>
            MANAGE
          </div>
          <div className="nav-list">
            {nav('/sources', 'Log sources', Server)}
            {canIngest && nav('/parsers', 'Parser lab', BookOpen)}
            {nav('/rules', 'Detection rules', SlidersHorizontal)}
            {canExport && nav('/reports', 'Reports', FileBarChart2)}
            {canAdmin && nav('/audit', 'Audit trail', Activity)}
            {canAdmin && nav('/settings', 'Settings', Settings2)}
          </div>
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-card">
            <ShieldCheck size={20} />
            <strong>Private by design</strong>
            <p>
              Your data stays in your installation.
              <br />
              Every alert comes with an explanation.
            </p>
            <Link className="text-link" to="/privacy" style={{ fontSize: 10, marginTop: 8 }}>
              Our privacy approach <ArrowUpRight size={11} />
            </Link>
          </div>
          <div className="user-mini">
            <Link className="avatar" to="/profile" aria-label="Open your profile">
              {user.name
                .split(' ')
                .map((part) => part[0])
                .slice(0, 2)
                .join('')}
            </Link>
            <div>
              <strong>{user.name}</strong>
              <small>{workspace.role.replaceAll('_', ' ')}</small>
            </div>
            <button
              className="icon-button"
              onClick={logout}
              aria-label="Sign out"
              disabled={action.busy}
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setMenu(!menu)}
            aria-label={menu ? 'Close navigation' : 'Open navigation'}
            aria-expanded={menu}
          >
            {menu ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={12} />
            <strong>{section}</strong>
          </div>
          <div className="top-actions">
            <form className="global-search" onSubmit={search}>
              <Search size={15} />
              <input
                name="q"
                ref={searchRef}
                aria-label="Search all events"
                placeholder="Search events…"
                maxLength={200}
              />
              <kbd>/</kbd>
            </form>
            <span className="top-separator" />
            <ThemeToggle />
            <Link className="icon-button" to="/notifications" aria-label="Notifications">
              <Bell size={17} />
            </Link>
            <Link className="icon-button" to="/security" aria-label="Security settings">
              <CircleHelp size={17} />
            </Link>
            <Link className="avatar" to="/profile" aria-label="Your profile">
              <UserRound size={16} />
            </Link>
          </div>
        </header>
        <main className="main-content" id="main-content">
          {health.data?.status !== 'ready' && health.data && (
            <div className="callout warning">
              <Activity size={16} />
              <p>
                Background worker is unavailable. Queued imports and reports will resume when it
                reconnects.
              </p>
            </div>
          )}
          <Outlet />
        </main>
        <footer className="footer">
          <span>
            <span
              className="status-dot"
              style={{ color: health.data?.status === 'ready' ? 'var(--accent)' : 'var(--amber)' }}
            />
            {health.data?.status === 'ready'
              ? 'All systems operational'
              : 'Checking service health'}
            <span>·</span>UTC storage / {user.timezone} display
          </span>
          <span>
            LogSentinel AI v1.0 <span>·</span>
            <Link to="/privacy">Privacy</Link>
            <span>·</span>
            <Link to="/terms">Responsible use</Link>
          </span>
        </footer>
      </div>
    </div>
  );
}
