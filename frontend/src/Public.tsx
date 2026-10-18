import { useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  FileInput,
  Fingerprint,
  LockKeyhole,
  Moon,
  ShieldCheck,
  Sparkles,
  Sun,
} from 'lucide-react';
import { api } from './api';
import { useTheme, useToast } from './context';
import type { User } from './types';
import { Submit } from './components';

export function Brand() {
  return (
    <Link className="brand" to="/">
      <span className="brand-icon">
        <ShieldCheck size={23} strokeWidth={2.1} />
      </span>
      <span>
        LogSentinel<em>AI</em>
      </span>
    </Link>
  );
}
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      className="icon-button"
      onClick={toggle}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
export function PublicFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="public-shell">
      <nav className="public-nav" aria-label="Public navigation">
        <Brand />
        <div>
          <ThemeToggle />
          <Link className="button secondary" to="/login">
            Open console <ArrowRight size={14} />
          </Link>
        </div>
      </nav>
      {children}
      <footer className="public-footer">
        <span>© {new Date().getFullYear()} LogSentinel AI · Built for defenders.</span>
        <div>
          <Link to="/privacy">Privacy notice</Link>
          <Link to="/terms">Terms of use</Link>
        </div>
      </footer>
    </div>
  );
}
export function Landing() {
  return (
    <PublicFrame>
      <main className="hero">
        <span className="live-pill">
          <Sparkles size={13} /> EXPLAINABLE SECURITY. PRIVATE BY DESIGN.
        </span>
        <h1>
          Clarity in every log.
          <br />
          <span>Confidence in every investigation.</span>
        </h1>
        <p>
          Turn noisy server logs into useful security insights. Find unusual activity, understand
          the evidence, and keep your team one step ahead.
        </p>
        <div className="hero-actions">
          <Link className="button" to="/login">
            Explore your workspace <ArrowRight size={17} />
          </Link>
          <Link className="button secondary" to="/privacy">
            <LockKeyhole size={16} /> Your data stays yours
          </Link>
        </div>
        <p className="tiny">
          No external AI service required. No automated blocking. You stay in control.
        </p>
      </main>
      <section className="panel hero-console" aria-label="How LogSentinel works">
        <div className="hero-console-header">
          <Brand />
          <span className="live-pill">
            <span className="status-dot" /> A clear path from signal to insight
          </span>
        </div>
        <div className="hero-flow">
          {[
            {
              Icon: FileInput,
              title: '01 / Collect',
              body: 'Import authorized files or connect a source using scoped API keys.',
            },
            {
              Icon: Fingerprint,
              title: '02 / Protect',
              body: 'Normalize, redact and correlate events before they reach storage.',
            },
            {
              Icon: Activity,
              title: '03 / Understand',
              body: 'Find patterns with versioned rules and explainable statistical baselines.',
            },
            {
              Icon: ShieldCheck,
              title: '04 / Investigate',
              body: 'Review evidence, collaborate on alerts and export useful reports.',
            },
          ].map(({ Icon, title, body }) => (
            <article className="flow-card" key={title}>
              <Icon size={25} />
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>
    </PublicFrame>
  );
}

export function AuthPage({ mode }: { mode: 'login' | 'forgot' | 'reset' }) {
  const status = useQuery({
    queryKey: ['auth-status'],
    queryFn: () =>
      api<{ setup_required: boolean; password_reset_delivery: boolean }>('/auth/status'),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const navigate = useNavigate();
  const queries = useQueryClient();
  const toast = useToast();
  const [search] = useSearchParams();
  const setup = mode === 'login' && status.data?.setup_required;
  const title =
    mode === 'forgot'
      ? 'Reset your password'
      : mode === 'reset'
        ? 'Choose a new password'
        : setup
          ? 'Create your workspace'
          : 'Welcome back';
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (mode === 'forgot') {
        const result = await api<{ message: string }>('/auth/forgot-password', 'POST', {
          email: values.email,
        });
        setMessage(result.message);
      } else if (mode === 'reset') {
        await api('/auth/reset-password', 'POST', {
          token: search.get('token') ?? '',
          password: values.password,
        });
        toast('Password changed. Sign in to continue.');
        navigate('/login');
      } else {
        const user = await api<User>(
          setup ? '/auth/setup' : '/auth/login',
          'POST',
          setup ? values : { email: values.email, password: values.password },
        );
        localStorage.setItem('ls_workspace', user.workspaces[0].id);
        queries.setQueryData(['session'], user);
        navigate('/dashboard');
      }
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Unable to continue');
    } finally {
      setBusy(false);
    }
  }
  return (
    <PublicFrame>
      <main className="auth-card">
        <div className="eyebrow">YOUR PRIVATE SECURITY CONSOLE</div>
        <h1>{title}</h1>
        <p>
          {setup
            ? 'Create the first administrator. Public registration closes as soon as setup is complete.'
            : mode === 'login'
              ? 'Sign in to see the signals that matter.'
              : 'Recovery links expire after 30 minutes and work once.'}
        </p>
        {error && (
          <div className="callout error" role="alert">
            {error}
          </div>
        )}
        {message ? (
          <div className="callout" role="status">
            {message}
          </div>
        ) : (
          <form onSubmit={submit}>
            {setup && (
              <>
                <label className="field">
                  Your name
                  <input name="name" autoComplete="name" required maxLength={100} />
                </label>
                <label className="field">
                  Workspace name
                  <input
                    name="workspace"
                    required
                    defaultValue="My security workspace"
                    maxLength={100}
                  />
                </label>
              </>
            )}
            {mode !== 'reset' && (
              <label className="field">
                Email address
                <input
                  name="email"
                  type="email"
                  autoComplete="username"
                  placeholder="you@company.com"
                  required
                  maxLength={254}
                />
              </label>
            )}
            {mode !== 'forgot' && (
              <label className="field">
                {mode === 'reset' ? 'New password' : 'Password'}
                <input
                  name="password"
                  type="password"
                  autoComplete={setup || mode === 'reset' ? 'new-password' : 'current-password'}
                  required
                  minLength={setup || mode === 'reset' ? 12 : 1}
                  maxLength={128}
                />
                {(setup || mode === 'reset') && (
                  <span className="field-hint">
                    Use a unique passphrase of at least 12 characters.
                  </span>
                )}
              </label>
            )}
            <Submit busy={busy || status.isPending}>
              {mode === 'forgot'
                ? 'Send recovery link'
                : mode === 'reset'
                  ? 'Change password'
                  : setup
                    ? 'Create secure workspace'
                    : 'Sign in to workspace'}{' '}
              <ArrowRight size={15} />
            </Submit>
          </form>
        )}
        {status.error && <p role="alert">The API is unavailable. Start the backend and refresh.</p>}
        <div className="auth-footer">
          <Link to={mode === 'login' ? '/forgot-password' : '/login'}>
            {mode === 'login' ? 'Forgot password?' : 'Back to sign in'}
          </Link>
          <span>
            <LockKeyhole size={11} /> Secure, private access
          </span>
        </div>
        {mode === 'forgot' && status.data && !status.data.password_reset_delivery && (
          <p className="tiny" style={{ marginTop: 18 }}>
            Email delivery is not configured on this installation. Your administrator can generate a
            recovery link using the local CLI.
          </p>
        )}
      </main>
    </PublicFrame>
  );
}
export function Legal({ privacy }: { privacy: boolean }) {
  return (
    <PublicFrame>
      <main className="legal-content">
        <div className="eyebrow">TRANSPARENCY & TRUST</div>
        <h1>{privacy ? 'Your logs. Your control.' : 'Responsible use, by design.'}</h1>
        {(privacy
          ? [
              [
                'What we store',
                'LogSentinel stores normalized, redacted log events, cryptographic fingerprints, investigation notes, account records and audit history in your installation. Raw-message storage is unavailable. Source and user identifiers are hashed with an installation-specific secret.',
              ],
              [
                'Where your data goes',
                'Core parsing and anomaly detection run locally. Logs are not sent to an external AI provider. Optional password-reset email requires your configured SMTP relay and contains only an expiring reset link.',
              ],
              [
                'Access and retention',
                'Workspace roles control access. Administrators configure retention and export policies. Automatic retention is opt-in; manual cleanup requires a preview and confirmation. Exports contain redacted data and must be handled with care.',
              ],
              [
                'Cookies and recovery',
                'HTTP-only session cookies authenticate your browser. A separate CSRF cookie protects state changes. Theme and workspace preferences are stored locally. Contact your installation operator to request access, correction or account assistance.',
              ],
            ]
          : [
              [
                'Authorized monitoring only',
                'Only ingest logs from systems you own or are explicitly authorized to monitor. Do not use this application to collect credentials, attack systems, evade access controls or monitor people without an appropriate basis.',
              ],
              [
                'Interpret observations carefully',
                'Anomalies are probabilistic observations, not proof of wrongdoing. Detection rules require tuning and data-quality review. Confirm evidence with authorized system owners before acting.',
              ],
              [
                'Human control',
                'LogSentinel does not scan targets, exploit vulnerabilities, automatically block addresses or disable accounts. Investigation steps are recommendations for an authorized operator.',
              ],
              [
                'Operator responsibilities',
                'Protect installation credentials, configure HTTPS, maintain backups, review retention and privacy policies, and restrict access. This application is a monitoring aid and does not guarantee detection of every security incident.',
              ],
            ]
        ).map(([title, text]) => (
          <section key={title}>
            <h2>{title}</h2>
            <p>{text}</p>
          </section>
        ))}
      </main>
    </PublicFrame>
  );
}
