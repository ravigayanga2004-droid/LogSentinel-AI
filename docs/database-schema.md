# Database schema

The initial Alembic revision defines tables, foreign keys, uniqueness and indexes. `alembic check` detects drift. JSON columns select JSONB on PostgreSQL and JSON on SQLite. All timestamps represent UTC; SQLite's naive returned values are normalized before comparison/display.

| Table | Purpose and boundaries |
| --- | --- |
| `users` | Unique account email, Argon2id hash, active flag, display timezone |
| `workspaces` | Workspace name and version-controlled privacy/retention policy shape |
| `workspace_members` | Composite workspace/user primary key and one of four fixed roles |
| `sessions` | Hashed opaque session and CSRF secrets; user and expiry |
| `password_reset_tokens` | Hashed, expiring, atomically consumed recovery tokens |
| `rate_buckets` | Shared atomic counters; expired buckets are cleaned by maintenance |
| `log_sources` | Parser, environment, enabled state, silence threshold and received/parsed/error timestamps |
| `api_keys` | Hashed secret, visible prefix, workspace/source binding and revocation |
| `jobs` | Kind, lease, attempts, safe payload, cursor/progress, result and idempotency key |
| `events` | Normalized redacted evidence, entity hashes, timestamps, classification and fingerprints |
| `detection_rules` | Configurable kind, threshold, window, scope/exclusions, severity, cooldown and version |
| `baselines` | Per-source feature distribution, trust threshold and reset/model version |
| `alerts` | Lifecycle, explanation, evidence count, assignment, tags, suppression and resolution |
| `alert_events` | Composite alert/event evidence references; event retention cascades these links |
| `alert_notes` | Workspace-scoped author, redacted note and evidence identifiers |
| `saved_searches` | Personal workspace-scoped names and validated event filters |
| `reports` | Authorized creator, filters, format, state and redacted generated content |
| `audit_logs` | Workspace actor, action, resource, safe metadata and timestamp |
| `notifications` | Workspace/member destination and per-user read state |
| `worker_heartbeats` | Process identity and last heartbeat |

Events index timestamp, workspace/time, source, event type, category, severity, service, username hash, IP hash, HTTP status, parse status and anomaly score. Source/fingerprint/dedup-bucket uniqueness prevents duplicate storage; a duplicate counter preserves received-record counts. Workspace/idempotency-key uniqueness protects queued imports. Alert deduplication has its own unique key. Baselines are unique per source/feature.

Frequently queried fields are columns. Optional application, destination hash/port, action, process identifier, user agent, Windows event identifier, correlation/request identifier, parser line number and job reference live in redacted `details`. Source type and source host configuration are joined from the source; parsed hosts also have an event column. Original usernames are replaced by hashes. `fingerprint` is an HMAC of the original canonical input; no recoverable raw message is stored. Parser version defaults to 1.0 and alert rule versions are retained.

Normal UI operations never delete alerts. Retention removes only expired resolved/false-positive alerts, their notes and evidence links. Open investigations survive alert retention, although separately expired event evidence can disappear; explanation and counts remain. Deletion is recorded with a fresh audit summary. Accounts are not hard-deleted through the normal UI.

The single installation secret protects correlation hashes; rotate it only with a planned baseline/fingerprint migration. Database backups and the secret must be preserved together. Never run schema downgrades on important data without a reviewed backup and migration plan.
