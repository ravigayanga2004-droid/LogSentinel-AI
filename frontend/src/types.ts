export type Role = 'administrator' | 'analyst' | 'viewer' | 'source_admin';
export interface Workspace {
  id: string;
  name: string;
  role: Role;
}
export interface User {
  id: string;
  name: string;
  email: string;
  timezone: string;
  workspaces: Workspace[];
}
export interface Source {
  id: string;
  name: string;
  type: string;
  parser: string;
  description: string;
  host: string;
  environment: string;
  enabled: boolean;
  silence_minutes: number;
  health: string;
  health_score: number;
  event_count: number;
  parse_failures: number;
  last_event_at: string | null;
  events_per_minute: number;
  average_latency_seconds: number;
}
export interface LogEvent {
  id: string;
  timestamp: string;
  source_id: string;
  severity: string;
  event_type: string;
  category: string;
  message: string;
  service: string;
  source_ip_hash: string;
  username_hash: string;
  status_code: number | null;
  url_path: string;
  parser_name: string;
  parser_version: string;
  parse_status: string;
  anomaly_score: number;
  duplicates: number;
  details: Record<string, unknown>;
  related?: LogEvent[];
}
export interface Note {
  id: string;
  body: string;
  author_id: string;
  created_at: string;
  evidence: string[];
}
export interface Audit {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_id: string;
  details: Record<string, unknown>;
  created_at: string;
}
export interface Alert {
  id: string;
  title: string;
  description: string;
  severity: string;
  confidence: number;
  status: string;
  source_id: string;
  rule_id: string;
  rule_version: number;
  first_seen: string;
  last_seen: string;
  created_at: string;
  event_count: number;
  assignee_id: string | null;
  tags: string[];
  resolution_reason: string;
  suppressed_until: string | null;
  explanation: {
    summary: string;
    observed: number;
    threshold: number;
    window_minutes: number;
    group: string;
    source_name: string;
    limitation: string;
    steps: string[];
    baseline: number | null;
  };
  events?: LogEvent[];
  notes?: Note[];
  history?: Audit[];
  similar?: Alert[];
}
export interface Rule {
  id: string;
  name: string;
  description: string;
  kind: string;
  enabled: boolean;
  severity: string;
  threshold: number;
  window_minutes: number;
  cooldown_minutes: number;
  group_by: string;
  config: Record<string, unknown>;
  version: number;
}
export interface Job {
  id: string;
  kind: string;
  source_id: string;
  status: string;
  progress: number;
  error: string | null;
  attempts: number;
  created_at: string;
  result: {
    total?: number;
    accepted?: number;
    rejected?: number;
    duplicates?: number;
    alerts_created?: number;
    redacted_records?: number;
    time_start?: string;
    time_end?: string;
    errors?: { line: number; message: string }[];
  };
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Series {
  name: string;
  value: number;
}
export interface Metrics {
  total_events: number;
  events_per_minute: number;
  open_alerts: number;
  high_alerts: number;
  anomalies: number;
  error_rate: number;
  parse_failure_rate: number;
  trend: { time: string; events: number; failed: number; success: number; errors: number }[];
  categories: Series[];
  http_status: Series[];
  top_users: Series[];
  top_ips: Series[];
  top_sources: Series[];
  severity: Series[];
  alert_status: Series[];
  sources: Source[];
  recent_alerts: Alert[];
  performance: { rule: string; alerts: number; false_positives: number }[];
}
export interface Member {
  id: string;
  name: string;
  email: string;
  role: Role;
  active: boolean;
}
export interface Report {
  id: string;
  title: string;
  format: string;
  status: string;
  created_at: string;
}
export interface Policy {
  event_retention_days: number;
  alert_retention_days: number;
  audit_retention_days: number;
  privacy_mode: boolean;
  exports_enabled: boolean;
  auto_retention: boolean;
  masks: string[];
  duplicate_window_minutes: number;
}
export interface Notification {
  id: string;
  title: string;
  link: string;
  read_by: string[];
  created_at: string;
}
