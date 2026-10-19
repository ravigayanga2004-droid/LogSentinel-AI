# Architecture and engineering decisions

The repository began with a README only. The implementation preserves its defensive log-analysis purpose while adding a runnable application. It uses two deployable application processes (FastAPI and a polling worker), a static React client, PostgreSQL and a shared redacted-staging volume. Nginx serves the console and proxies `/api` to keep cookies and CSRF same-origin.

## Data flow

1. An authenticated workspace member uploads a bounded authorized file, or a source-scoped API key submits a JSON batch.
2. Parsers normalize fields; privacy helpers remove secrets and pseudonymize identifiers before records reach staging. Invalid rows contain only safe errors and source line numbers.
3. A durable job record identifies the redacted staging file. A worker atomically claims it using a lease and attempt counter.
4. Ingestion writes at most 250 records per transaction, performs batched fingerprint checks, updates progress and commits the cursor together with its events. Retries resume after the last committed record.
5. Detection evaluates enabled versioned rules and historical baselines. Evidence references, explanation and cooldown deduplication accompany each alert.
6. Authorized users investigate, annotate and resolve alerts. Every sensitive action writes a workspace audit entry.
7. Report jobs produce redacted CSV or JSON; downloads recheck membership, export permission and policy.

## Boundaries

The browser is untrusted. Hiding navigation is a convenience; API dependencies validate sessions, CSRF, workspace membership, permission and resource scope. Machine keys have write access to exactly one enabled source and cannot read logs. No input is executed. No host connection, remote probe or arbitrary webhook request is made.

SQLAlchemy parameterizes values. Frequently filtered columns and workspace/timestamp combinations are indexed. Flexible structured metadata uses PostgreSQL JSONB and SQLite JSON. Alembic migrations are explicit and reviewed; application startup never auto-creates tables or seeds accounts.

The database queue avoids a separate Redis dependency. Jobs are durable across process restarts; leases expire after ten minutes, ingestion renews its lease per batch, and failed work backs off exponentially for at most three attempts. Polling also records worker health; readiness fails when the worker heartbeat is stale. Maintenance schedules detections each minute and optional daily retention.

## Stack deviations

- SQLite supports an easy local setup and isolated tests; production validation requires PostgreSQL.
- A custom CSS token system and native controls implement the console instead of Tailwind/shadcn. Shared dialogs, labels, focus styles and charts' data tables provide accessible interaction.
- Server-validated native forms replace React Hook Form/Zod. Pydantic is the authoritative schema.
- Standard-library robust statistics replace pandas/scikit-learn for the core engine. No optional external model is needed.
- Fixed role/permission mappings are version-controlled policy, rather than editable Role and Permission rows. See `security.py`.
- Parser definitions, rule types and model versions live in code; statistical summaries live in `baselines`. Events carry anomaly scores, and alerts retain evidence links; there is no redundant anomaly or model table.
- Event fingerprints and duplicate counters live on `events`; tags are a bounded JSON field. Privacy/retention policy is workspace JSON. This reduces joins and keeps transactional ownership clear.

## Scaling

Use PostgreSQL and a shared staging volume for multiple API/worker processes. Start with one worker and measure before increasing concurrency. Imports, API batches, reports, windows and pages are bounded; line formats stream. SQLite is for a single installation's development, not concurrent production workloads. Before very large deployments, add partitioning, explicit operational SLOs, connection-pool tuning, query plans and long-duration benchmarks.
