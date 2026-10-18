import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, FileUp, KeyRound, Plus, Search, Server, UploadCloud } from 'lucide-react';
import { api, headers, upload } from './api';
import { useAction, useAuth, useCan, useToast } from './context';
import {
  Badge,
  Confirm,
  Dialog,
  Empty,
  ErrorState,
  Loading,
  PageTitle,
  Pager,
  Panel,
  Submit,
  Time,
} from './components';
import type { Job, Page, Source } from './types';

interface Key {
  id: string;
  name: string;
  prefix: string;
  source_id: string;
  revoked: boolean;
  key?: string;
}
export function Sources() {
  const { workspace } = useAuth();
  const canManage = useCan('sources'),
    canIngest = useCan('ingest');
  const [search, setSearch] = useState('');
  const [importSource, setImportSource] = useState<Source | null>(null);
  const [keySource, setKeySource] = useState<Source | null>(null);
  const [revoke, setRevoke] = useState('');
  const [newKey, setNewKey] = useState('');
  const [jobPage, setJobPage] = useState(1);
  const action = useAction();
  const toast = useToast();
  const sources = useQuery({
    queryKey: ['sources', workspace.id],
    queryFn: () => api<{ items: Source[] }>('/sources'),
    refetchInterval: 15000,
  });
  const keys = useQuery({
    queryKey: ['keys', workspace.id],
    queryFn: () => api<{ items: Key[] }>('/keys'),
    enabled: canManage,
  });
  const jobs = useQuery({
    queryKey: ['jobs', workspace.id, jobPage],
    queryFn: () => api<Page<Job>>(`/jobs?page_number=${jobPage}`),
    enabled: canIngest,
    refetchInterval: 3000,
  });
  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const result = await action.run(
      () => api<Key>(`/sources/${keySource?.id}/keys`, 'POST', { name: data.get('name') }),
      'API key created',
    );
    if (result?.key) {
      setNewKey(result.key);
      setKeySource(null);
    }
  }
  const filtered = sources.data?.items.filter((row) =>
    `${row.name} ${row.host} ${row.type}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <PageTitle
        eyebrow="KEEP YOUR VISIBILITY INTACT"
        title="Log sources"
        description="Connect authorized systems, import logs, and watch your ingestion health."
        actions={
          canManage && (
            <Link className="button" to="/sources/new">
              <Plus size={15} /> Add log source
            </Link>
          )
        }
      />
      <div className="toolbar">
        <label className="filter-control search">
          <Search size={14} />
          <input
            aria-label="Search sources"
            placeholder="Search by name, host or type…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <span className="spacer" />
        <span className="muted tiny">Health updates every 15 seconds</span>
      </div>
      {sources.isPending ? (
        <Loading />
      ) : sources.error ? (
        <ErrorState error={sources.error} retry={() => sources.refetch()} />
      ) : !filtered?.length ? (
        <Panel>
          <Empty
            title="Connect your first log source"
            description="Add a source, choose its parser, and upload a file or create a scoped ingestion key."
            action={
              canManage && (
                <Link className="button" to="/sources/new">
                  Add a source
                </Link>
              )
            }
          />
        </Panel>
      ) : (
        <div className="grid-3">
          {filtered.map((source) => (
            <article className="panel source-card" key={source.id}>
              <div className="source-card-top">
                <span className="source-icon">
                  <Server size={22} />
                </span>
                <Badge value={source.health} />
              </div>
              <h2>{source.name}</h2>
              <p>
                {source.host || 'Host not specified'} · {source.environment}
              </p>
              <dl className="definition-list">
                <dt>Parser</dt>
                <dd>{source.parser} v1.0</dd>
                <dt>Events / 24h</dt>
                <dd>{source.event_count.toLocaleString()}</dd>
                <dt>Parsing failures</dt>
                <dd>{source.parse_failures}</dd>
                <dt>Health score</dt>
                <dd>{source.health_score}%</dd>
                <dt>Ingestion / min</dt>
                <dd>{source.events_per_minute}</dd>
                <dt>Last received</dt>
                <dd>
                  <Time value={source.last_event_at} />
                </dd>
              </dl>
              <footer>
                {canIngest && (
                  <button
                    className="button small"
                    disabled={!source.enabled}
                    onClick={() => setImportSource(source)}
                  >
                    <FileUp size={12} /> Import logs
                  </button>
                )}
                {canManage && (
                  <>
                    <Link className="button secondary small" to={`/sources/${source.id}/edit`}>
                      Edit source
                    </Link>
                    <button
                      className="icon-button"
                      aria-label={`Create API key for ${source.name}`}
                      onClick={() => setKeySource(source)}
                    >
                      <KeyRound size={14} />
                    </button>
                  </>
                )}
              </footer>
            </article>
          ))}
        </div>
      )}
      {canIngest && (
        <Panel
          title="Ingestion & background jobs"
          subtitle="Durable, resumable processing with bounded retries"
        >
          {jobs.isPending ? (
            <Loading />
          ) : jobs.error ? (
            <ErrorState error={jobs.error} />
          ) : !jobs.data?.items.length ? (
            <Empty
              title="No imports yet"
              description="Use Import logs on a source to process your first file."
            />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Result</th>
                    <th>Created</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.data.items.map((job) => (
                    <tr key={job.id}>
                      <td>
                        {job.kind}
                        <div className="cell-description">{job.id.slice(0, 8)}</div>
                      </td>
                      <td>
                        {sources.data?.items.find((row) => row.id === job.source_id)?.name ??
                          'Workspace'}
                      </td>
                      <td>
                        <Badge value={job.status} />
                      </td>
                      <td>
                        {job.progress}%
                        <div className="progress">
                          <div style={{ width: `${job.progress}%` }} />
                        </div>
                      </td>
                      <td>
                        {job.result.total !== undefined ? (
                          <>
                            <span>
                              {job.result.accepted} valid · {job.result.rejected} failed ·{' '}
                              {job.result.duplicates} duplicate
                            </span>
                            <div className="cell-description">
                              {job.result.alerts_created ?? 0} alerts ·{' '}
                              {job.result.redacted_records ?? 0} records privacy-processed
                            </div>
                          </>
                        ) : (
                          (job.error ?? '—')
                        )}
                        {job.result.errors?.length ? (
                          <details>
                            <summary>{job.result.errors.length} parsing errors</summary>
                            {job.result.errors.map((error) => (
                              <p className="tiny" key={error.line}>
                                Line {error.line}: {error.message}
                              </p>
                            ))}
                          </details>
                        ) : null}
                      </td>
                      <td>
                        <Time value={job.created_at} />
                      </td>
                      <td>
                        {job.status === 'failed' ? (
                          <button
                            className="button secondary small"
                            disabled={action.busy}
                            onClick={() =>
                              action.run(
                                () => api(`/jobs/${job.id}/retry`, 'POST'),
                                'Job queued for retry',
                              )
                            }
                          >
                            Retry
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {jobs.data && <Pager page={jobPage} total={jobs.data.total} setPage={setJobPage} />}
        </Panel>
      )}
      {canManage && (
        <Panel
          title="Scoped ingestion keys"
          subtitle="Each key can write only to its configured source. Keys cannot read events."
        >
          {keys.error ? (
            <ErrorState error={keys.error} />
          ) : keys.data?.items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Source</th>
                    <th>Key prefix</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {keys.data.items.map((key) => (
                    <tr key={key.id}>
                      <td>{key.name}</td>
                      <td>{sources.data?.items.find((row) => row.id === key.source_id)?.name}</td>
                      <td>
                        <code>{key.prefix}…</code>
                      </td>
                      <td>
                        <Badge value={key.revoked ? 'disabled' : 'healthy'} />
                      </td>
                      <td>
                        {!key.revoked && (
                          <button className="button ghost small" onClick={() => setRevoke(key.id)}>
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No API keys created"
              description="Use the key icon on a source to create its first ingestion credential."
            />
          )}
        </Panel>
      )}
      {importSource && <ImportDialog source={importSource} close={() => setImportSource(null)} />}
      {keySource && (
        <Dialog title={`Create key · ${keySource.name}`} onClose={() => setKeySource(null)}>
          <form onSubmit={createKey}>
            <label className="field">
              Key name
              <input name="name" required maxLength={100} placeholder="e.g. Production collector" />
            </label>
            <div className="form-actions">
              <Submit busy={action.busy}>Create scoped key</Submit>
            </div>
          </form>
        </Dialog>
      )}
      {newKey && (
        <Dialog title="Copy your ingestion key" onClose={() => setNewKey('')}>
          <div className="callout warning">
            This secret is shown once. Store it securely outside the repository.
          </div>
          <label className="field">
            API key
            <input readOnly value={newKey} onFocus={(event) => event.target.select()} />
          </label>
          <div className="form-actions">
            <button
              className="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(newKey);
                  toast('Key copied');
                } catch {
                  toast('Select the key and copy it using your keyboard.', true);
                }
              }}
            >
              <Copy size={14} /> Copy key
            </button>
          </div>
          <p className="tiny" style={{ marginTop: 16 }}>
            Send JSON batches to POST /api/ingest with the X-API-Key header. See docs/ingestion.md
            for examples.
          </p>
        </Dialog>
      )}
      {revoke && (
        <Confirm
          title="Revoke ingestion key?"
          description="This collector will stop authenticating immediately. You can create a replacement key afterward."
          onClose={() => setRevoke('')}
          busy={action.busy}
          onConfirm={async () => {
            const result = await action.run(() => api(`/keys/${revoke}`, 'DELETE'), 'Key revoked');
            if (result) setRevoke('');
          }}
        />
      )}
    </>
  );
}
export function SourceEditor() {
  const { id } = useParams();
  const { workspace } = useAuth();
  const can = useCan('sources');
  const query = useQuery({
    queryKey: ['source', workspace.id, id],
    queryFn: () => api<Source>(`/sources/${id}`),
    enabled: !!id,
  });
  if (!can)
    return <ErrorState error={new Error('Source administration permission is required.')} />;
  return (
    <>
      <Link className="text-link" to="/sources">
        <ArrowLeft size={13} /> Back to sources
      </Link>
      <PageTitle
        title={id ? 'Edit log source' : 'Connect a log source'}
        description="Configure an authorized system. This platform reads submitted logs and never scans the host."
      />
      {id && query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : (
        <SourceForm key={id ?? 'new'} source={query.data} />
      )}
    </>
  );
}
function SourceForm({ source }: { source?: Source }) {
  const action = useAction();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState(false);
  const [pending, setPending] = useState<Record<string, unknown> | null>(null);
  async function save(values: Record<string, unknown>) {
    const result = await action.run(
      () => api(source ? `/sources/${source.id}` : '/sources', source ? 'PUT' : 'POST', values),
      source ? 'Source updated' : 'Source connected',
    );
    if (result) navigate('/sources');
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const values = {
      ...Object.fromEntries(data),
      enabled: data.has('enabled'),
      silence_minutes: Number(data.get('silence_minutes')),
    };
    if (source?.enabled && !values.enabled) {
      setPending(values);
      setConfirm(true);
    } else save(values);
  }
  return (
    <Panel title="Source configuration">
      <form className="panel-content form-stack" onSubmit={submit}>
        <div className="fields-grid">
          <label className="field">
            Source name
            <input
              name="name"
              defaultValue={source?.name}
              required
              maxLength={100}
              placeholder="e.g. Production SSH"
            />
          </label>
          <label className="field">
            Source type
            <select name="type" defaultValue={source?.type ?? 'application'}>
              {['linux_auth', 'web', 'application', 'database', 'firewall', 'cloud', 'custom'].map(
                (value) => (
                  <option key={value}>{value}</option>
                ),
              )}
            </select>
          </label>
          <label className="field">
            Parser
            <select name="parser" defaultValue={source?.parser ?? 'auto'}>
              {[
                'auto',
                'json',
                'linux_auth',
                'nginx',
                'apache',
                'key_value',
                'generic',
                'windows',
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Host label
            <input
              name="host"
              defaultValue={source?.host}
              maxLength={100}
              placeholder="auth-prod-01"
            />
          </label>
          <label className="field">
            Environment
            <input
              name="environment"
              defaultValue={source?.environment ?? 'production'}
              maxLength={30}
              required
            />
          </label>
          <label className="field">
            Silence threshold (minutes)
            <input
              name="silence_minutes"
              type="number"
              min={1}
              max={10080}
              defaultValue={source?.silence_minutes ?? 60}
              required
            />
          </label>
        </div>
        <label className="field">
          Description
          <textarea name="description" maxLength={2000} defaultValue={source?.description} />
        </label>
        <label className="checkbox-row">
          <input name="enabled" type="checkbox" defaultChecked={source?.enabled ?? true} /> Enable
          ingestion for this source
        </label>
        <div className="form-actions">
          <Link className="button secondary" to="/parsers">
            Test a parser
          </Link>
          <Submit busy={action.busy}>{source ? 'Save source' : 'Connect source'}</Submit>
        </div>
      </form>
      {confirm && (
        <Confirm
          title="Disable this source?"
          description="New imports and API ingestion will be rejected until the source is enabled again. Existing events remain available."
          onClose={() => setConfirm(false)}
          busy={action.busy}
          onConfirm={() => {
            if (pending) save(pending);
          }}
        />
      )}
    </Panel>
  );
}
function ImportDialog({ source, close }: { source: Source; close: () => void }) {
  const action = useAction();
  const [progress, setProgress] = useState(0);
  const [csv, setCsv] = useState(false);
  const [preview, setPreview] = useState<unknown>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const toast = useToast();
  function body(form: HTMLFormElement) {
    const data = new FormData(form);
    const timestamp = String(data.get('timestamp_column') ?? '');
    const message = String(data.get('message_column') ?? '');
    data.delete('timestamp_column');
    data.delete('message_column');
    data.set('mapping', csv ? JSON.stringify({ timestamp, message }) : '{}');
    return data;
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = body(event.currentTarget);
    const result = await action.run(
      () => upload(source.id, data, setProgress),
      'Import queued. Processing progress appears in the jobs table.',
    );
    if (result) close();
  }
  async function previewFile(form: HTMLFormElement | null) {
    if (!form || !form.reportValidity()) return;
    setPreviewBusy(true);
    try {
      const response = await fetch(`/api/sources/${source.id}/preview`, {
        method: 'POST',
        headers: headers(),
        body: body(form),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Cannot preview this file');
      setPreview(data);
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Preview failed', true);
    } finally {
      setPreviewBusy(false);
    }
  }
  return (
    <Dialog title={`Import logs · ${source.name}`} onClose={action.busy ? () => {} : close}>
      <form className="form-stack" onSubmit={submit}>
        <div className="upload-zone">
          <UploadCloud size={30} />
          <h3>A clearer picture starts with your logs</h3>
          <p>UTF-8 .log, .txt, .json, .jsonl or .csv · up to 10 MB</p>
          <input
            aria-label="Log file"
            name="file"
            type="file"
            accept=".log,.txt,.json,.jsonl,.csv"
            required
            onChange={(event) => {
              setCsv(event.target.files?.[0]?.name.toLowerCase().endsWith('.csv') ?? false);
              setPreview(null);
            }}
          />
        </div>
        {csv && (
          <div className="fields-grid">
            <label className="field">
              Timestamp column
              <input name="timestamp_column" required placeholder="timestamp" />
            </label>
            <label className="field">
              Message column
              <input name="message_column" required placeholder="message" />
            </label>
          </div>
        )}
        <label className="checkbox-row">
          <input type="checkbox" name="allow_partial" value="true" /> Allow partial import and
          record safe errors for invalid lines
        </label>
        <p className="tiny">
          Input is redacted before staging. Raw content is discarded. CSV requires an explicit
          timestamp and message mapping.
        </p>
        {action.busy && (
          <div role="status">
            Uploading {progress}%
            <div className="progress">
              <div style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}
        {preview !== null && (
          <div>
            <h3>Redacted preview · no events imported</h3>
            <pre>{JSON.stringify(preview, null, 2)}</pre>
          </div>
        )}
        <div className="form-actions">
          <button
            className="button secondary"
            type="button"
            disabled={previewBusy || action.busy}
            onClick={(event) => previewFile(event.currentTarget.form)}
          >
            {previewBusy ? 'Validating…' : 'Preview & validate'}
          </button>
          <Submit busy={action.busy}>Import log file</Submit>
        </div>
      </form>
    </Dialog>
  );
}
