import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, FlaskConical, Play, Plus, Search, ShieldCheck } from 'lucide-react';
import { api } from './api';
import { useAction, useAuth, useCan, useToast } from './context';
import {
  Badge,
  Confirm,
  Dialog,
  Empty,
  ErrorState,
  Loading,
  PageTitle,
  Panel,
  Submit,
  severities,
} from './components';
import type { Rule } from './types';

const kinds = [
  'failed_login',
  'success_after_failures',
  'http_401',
  'http_403',
  'error_spike',
  'volume_spike',
  'sensitive_path',
  'new_entity',
  'many_users',
  'many_sources',
  'unusual_process',
  'source_silence',
  'parser_failure',
  'out_of_hours',
  'severity_spike',
  'statistical',
];
function ruleBody(rule: Rule) {
  return {
    name: rule.name,
    description: rule.description,
    kind: rule.kind,
    enabled: rule.enabled,
    severity: rule.severity,
    threshold: rule.threshold,
    window_minutes: rule.window_minutes,
    cooldown_minutes: rule.cooldown_minutes,
    group_by: rule.group_by,
    config: rule.config,
  };
}
interface Baseline {
  id: string;
  source_id: string;
  feature: string;
  version: number;
  stats: { trusted: boolean; samples: number; median?: number; mad?: number; threshold?: number };
}
export function Rules() {
  const { workspace } = useAuth();
  const can = useCan('rules');
  const [search, setSearch] = useState('');
  const [test, setTest] = useState<unknown>(null);
  const [reset, setReset] = useState('');
  const action = useAction();
  const rules = useQuery({
    queryKey: ['rules', workspace.id],
    queryFn: () => api<{ items: Rule[] }>('/rules'),
  });
  const baselines = useQuery({
    queryKey: ['baselines', workspace.id],
    queryFn: () => api<{ items: Baseline[] }>('/baselines'),
  });
  async function testRule(id: string) {
    const result = await action.run(
      () => api(`/rules/${id}/test`, 'POST'),
      'Rule evaluated without creating alerts',
    );
    if (result) setTest(result);
  }
  return (
    <>
      <PageTitle
        eyebrow="TRANSPARENT BY DESIGN"
        title="Detection rules"
        description="Tune the signals to your environment. Every change creates a new rule version."
        actions={
          can && (
            <>
              <button
                className="button secondary"
                disabled={action.busy}
                onClick={() =>
                  action.run(
                    () => api('/detection/run', 'POST'),
                    'Detection queued. View job progress in Log sources.',
                  )
                }
              >
                <Play size={13} /> Run detection
              </button>
              <Link className="button" to="/rules/new">
                <Plus size={14} /> Create rule
              </Link>
            </>
          )
        }
      />
      <div className="toolbar">
        <label className="filter-control search">
          <Search size={14} />
          <input
            aria-label="Search detection rules"
            placeholder="Search rule names or types…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <span className="spacer" />
        <span className="live-pill">
          <ShieldCheck size={12} /> Explainable rules + robust statistics
        </span>
      </div>
      <Panel title="Rule library" subtitle="Rule-based, sequence and statistical detections">
        {rules.isPending ? (
          <Loading />
        ) : rules.error ? (
          <ErrorState error={rules.error} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Severity</th>
                  <th>Threshold / window</th>
                  <th>Cooldown</th>
                  <th>Version</th>
                  <th>State</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.data.items
                  .filter((rule) =>
                    `${rule.name} ${rule.kind}`.toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((rule) => (
                    <tr key={rule.id}>
                      <td className="primary-cell">
                        {rule.name}
                        <div className="cell-description">{rule.kind.replaceAll('_', ' ')}</div>
                      </td>
                      <td>
                        <Badge value={rule.severity} />
                      </td>
                      <td>
                        {rule.threshold} / {rule.window_minutes}m
                      </td>
                      <td>{rule.cooldown_minutes}m</td>
                      <td>v{rule.version}</td>
                      <td>
                        <Badge value={rule.enabled ? 'healthy' : 'disabled'} />
                      </td>
                      <td>
                        {can ? (
                          <div style={{ display: 'flex', gap: 8 }}>
                            <Link className="button secondary small" to={`/rules/${rule.id}/edit`}>
                              Edit
                            </Link>
                            <button
                              className="button secondary small"
                              onClick={() => testRule(rule.id)}
                              disabled={action.busy}
                            >
                              <FlaskConical size={11} /> Test
                            </button>
                            <button
                              className="button ghost small"
                              disabled={action.busy}
                              onClick={() =>
                                action.run(
                                  () =>
                                    api(`/rules/${rule.id}`, 'PUT', {
                                      ...ruleBody(rule),
                                      enabled: !rule.enabled,
                                    }),
                                  rule.enabled ? 'Rule disabled' : 'Rule enabled',
                                )
                              }
                            >
                              {rule.enabled ? 'Disable' : 'Enable'}
                            </button>
                          </div>
                        ) : (
                          'Read only'
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel
        title="Behavioral baselines"
        subtitle="Five-minute event-count distributions · minimum 12 historical windows before trusting a baseline"
      >
        {baselines.data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Samples</th>
                  <th>Median</th>
                  <th>MAD</th>
                  <th>Trigger threshold</th>
                  <th>State</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {baselines.data.items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <code>{row.source_id.slice(0, 12)}…</code>
                    </td>
                    <td>{row.stats.samples}</td>
                    <td>{row.stats.median ?? '—'}</td>
                    <td>{row.stats.mad ?? '—'}</td>
                    <td>{row.stats.threshold?.toFixed(1) ?? '—'}</td>
                    <td>
                      <Badge value={row.stats.trusted ? 'healthy' : 'learning'} />
                    </td>
                    <td>
                      {can && (
                        <button className="button ghost small" onClick={() => setReset(row.id)}>
                          Reset baseline
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : baselines.error ? (
          <ErrorState error={baselines.error} />
        ) : (
          <Empty
            title="Baselines are learning"
            description="Import historical events and run detection to build a source baseline."
          />
        )}
      </Panel>
      {test !== null && (
        <Dialog title="Rule evaluation · test only" onClose={() => setTest(null)}>
          <p className="tiny">No alerts were created by this preview.</p>
          <pre>{JSON.stringify(test, null, 2)}</pre>
        </Dialog>
      )}
      {reset && (
        <Confirm
          title="Reset this baseline?"
          description="The baseline will return to learning mode and wait for sufficient new history before triggering statistical detections."
          onClose={() => setReset('')}
          busy={action.busy}
          onConfirm={async () => {
            const result = await action.run(
              () => api(`/baselines/${reset}/reset`, 'POST'),
              'Baseline reset',
            );
            if (result) setReset('');
          }}
        />
      )}
    </>
  );
}
export function RuleEditor() {
  const { id } = useParams();
  const { workspace } = useAuth();
  const can = useCan('rules');
  const query = useQuery({
    queryKey: ['rule', workspace.id, id],
    queryFn: () => api<Rule>(`/rules/${id}`),
    enabled: !!id,
  });
  if (!can) return <ErrorState error={new Error('Rule management permission is required.')} />;
  return (
    <>
      <Link className="text-link" to="/rules">
        <ArrowLeft size={13} /> Back to detection rules
      </Link>
      <PageTitle
        title={id ? 'Edit detection rule' : 'Create a detection rule'}
        description="Define a clear condition, a useful threshold, and a proportionate severity."
      />
      {id && query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : (
        <RuleForm key={id ?? 'new'} rule={query.data} />
      )}
    </>
  );
}
function RuleForm({ rule }: { rule?: Rule }) {
  const action = useAction();
  const toast = useToast();
  const navigate = useNavigate();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    let config;
    try {
      config = JSON.parse(String(data.get('config')));
    } catch {
      toast('Advanced configuration must be a JSON object.', true);
      return;
    }
    const body = {
      ...Object.fromEntries(data),
      threshold: Number(data.get('threshold')),
      window_minutes: Number(data.get('window_minutes')),
      cooldown_minutes: Number(data.get('cooldown_minutes')),
      enabled: data.has('enabled'),
      config,
    };
    const result = await action.run(
      () => api(rule ? `/rules/${rule.id}` : '/rules', rule ? 'PUT' : 'POST', body),
      rule ? 'New rule version saved' : 'Rule created',
    );
    if (result) navigate('/rules');
  }
  return (
    <Panel title="Detection configuration">
      <form className="panel-content form-stack" onSubmit={submit}>
        <div className="fields-grid">
          <label className="field">
            Rule name
            <input name="name" defaultValue={rule?.name} required maxLength={100} />
          </label>
          <label className="field">
            Detection type
            <select name="kind" defaultValue={rule?.kind ?? 'failed_login'}>
              {kinds.map((value) => (
                <option key={value} value={value}>
                  {value.replaceAll('_', ' ')}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Severity
            <select name="severity" defaultValue={rule?.severity ?? 'high'}>
              {severities.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Threshold
            <input
              name="threshold"
              type="number"
              min={1}
              max={100000}
              defaultValue={rule?.threshold ?? 5}
              required
            />
          </label>
          <label className="field">
            Time window (minutes)
            <input
              name="window_minutes"
              type="number"
              min={1}
              max={10080}
              defaultValue={rule?.window_minutes ?? 5}
              required
            />
          </label>
          <label className="field">
            Cooldown (minutes)
            <input
              name="cooldown_minutes"
              type="number"
              min={1}
              max={10080}
              defaultValue={rule?.cooldown_minutes ?? 30}
              required
            />
          </label>
          <label className="field">
            Group by
            <select name="group_by" defaultValue={rule?.group_by ?? 'source_ip_hash'}>
              {['source_ip_hash', 'username_hash', 'service', 'source_id'].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="field">
          Description
          <textarea name="description" defaultValue={rule?.description} maxLength={2000} />
        </label>
        <label className="field">
          Advanced configuration (JSON)
          <textarea
            name="config"
            defaultValue={JSON.stringify(rule?.config ?? {}, null, 2)}
            rows={6}
            maxLength={20000}
            spellCheck={false}
          />
          <span className="field-hint">
            Optional: source_ids, service, paths, excluded_ip_hashes, excluded_user_hashes,
            expected_processes, start_hour, end_hour. Hours use UTC. See docs/detection-engine.md.
          </span>
        </label>
        <label className="checkbox-row">
          <input name="enabled" type="checkbox" defaultChecked={rule?.enabled ?? true} /> Enable
          this rule
        </label>
        <div className="form-actions">
          <Submit busy={action.busy}>{rule ? 'Save new version' : 'Create detection rule'}</Submit>
        </div>
      </form>
    </Panel>
  );
}
export function ParserLab() {
  const [text, setText] = useState('');
  const [parser, setParser] = useState('auto');
  const [result, setResult] = useState<unknown>(null);
  const action = useAction();
  const can = useCan('ingest');
  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = await action.run(
      () => api('/parsers/test', 'POST', { text, parser }),
      'Parser preview complete. No events were imported.',
    );
    if (value) setResult(value);
  }
  if (!can) return <ErrorState error={new Error('Ingestion permission is required.')} />;
  return (
    <>
      <PageTitle
        eyebrow="SAFE INPUT / STRUCTURED OUTPUT"
        title="Parser lab"
        description="Try a sample, inspect normalized fields, and validate redaction before importing."
        actions={
          <button
            className="button secondary"
            onClick={() => {
              setParser('json');
              setText(
                JSON.stringify(
                  {
                    timestamp: new Date().toISOString(),
                    message: 'Synthetic request token=secret-example',
                    status_code: 403,
                    ip: '192.0.2.10',
                    path: '/admin?api_key=secret',
                    service: 'nginx',
                  },
                  null,
                  0,
                ),
              );
            }}
          >
            Load synthetic sample
          </button>
        }
      />
      <div className="grid-2">
        <Panel title="Sample input" subtitle="Test data only · first 100 lines · maximum 64 KiB">
          <form className="panel-content form-stack" onSubmit={submit}>
            <label className="field">
              Parser
              <select value={parser} onChange={(event) => setParser(event.target.value)}>
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
              Log sample
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={13}
                required
                maxLength={65536}
                placeholder="Paste an authorized sample. Pasted content is never executed."
                spellCheck={false}
              />
            </label>
            <Submit busy={action.busy}>
              <FlaskConical size={14} /> Test parser
            </Submit>
          </form>
        </Panel>
        <Panel
          title="Redacted output"
          subtitle="Format match, normalized fields and safe row-level errors"
        >
          {result !== null ? (
            <div className="panel-content">
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </div>
          ) : (
            <Empty
              title="Ready when you are"
              description="Paste a sample and test its parser to inspect redacted normalized output."
            />
          )}
        </Panel>
      </div>
    </>
  );
}
