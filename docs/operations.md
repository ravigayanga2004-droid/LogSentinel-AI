# Operating LogSentinel

## Routine checks

Check `/api/health`, `/api/ready`, Compose health state, worker heartbeat, oldest queued job age, failed jobs, disk usage, database size, source silence, parser failures and ingestion latency. The console shows source health and job progress; audit history records sensitive actions. Application logs are JSON metadata with request/job IDs, method, status and duration. They omit raw payloads, credentials, exception strings and query strings. Configure host/container log rotation with bounded size/file counts.

The worker polls the durable database queue, claims jobs with a ten-minute lease, renews ingestion leases per committed batch and retries failures with exponential backoff for at most three attempts. A crashed final attempt becomes failed after lease expiry. Periodic maintenance schedules source detections each minute, expires sessions/rate buckets and schedules optional daily retention. Configure external restart/monitoring for a stopped worker; the API continues to accept bounded queued work but readiness becomes degraded.

For a failed job, inspect its safe error and source configuration. Correct the parser/input policy, narrow oversized report ranges, enable the intended source or restore database/staging availability. Use Retry only after correcting the cause. Ingestion retries resume from the committed cursor and do not inflate duplicate counters. Report generation is idempotent because content/state are replaced transactionally. A disabled source rejects new imports and causes queued imports to retry/fail safely.

Completed import staging files are removed. Failed imports retain redacted files for review/retry. Unreferenced files can remain after a transaction failure, concurrent idempotency conflict or abrupt process termination. Review the staging directory and database references before manually removing abandoned files; there is no automatic orphan-file garbage collector. Protect this volume like event data and include it in disk monitoring. Cleanup rules must not remove files used by queued/running/failed retryable jobs.

## Backups and restore

Back up PostgreSQL with `pg_dump` to a protected host file, and preserve the installation secret and deployment configuration separately in a secure store. Back up the staging volume consistently with jobs if active imports must resume. Use encrypted storage and retention limits; exports and backups can retain data beyond the live database's cleanup.

Example inside the database container (the command writes a file in the container; copy it to protected backup storage using `docker cp`):

```text
docker compose --env-file .env.docker exec database pg_dump -U sentinel -d logsentinel -Fc -f /tmp/logsentinel.backup
docker cp logsentinel-database-1:/tmp/logsentinel.backup ./protected-backup-location/logsentinel.backup
```

The destination directory must already be protected and excluded from Git. Remove the temporary container copy after validating the backup. Schedule backups through your operator tooling; no automatic backup agent is bundled.

Restore into a **new, isolated database**, then validate schema, accounts, counts, evidence access and a sample import before cutover:

```text
pg_restore --no-owner --dbname="$RESTORE_DATABASE_URL" /protected/path/logsentinel.backup
```

Never restore with destructive flags into important live data without an explicit reviewed plan. Preserve the original secret so fingerprints and entity correlation remain stable. The application does not automatically move/migrate SQLite data into PostgreSQL; use a reviewed ETL procedure if preserving local data is required.

## Security events

Revoke an exposed ingestion key immediately and replace it on the authorized sender. Change compromised passwords to invalidate sessions. Restrict network access and preserve required evidence under your incident process. Rotating SECRET_KEY changes entity/fingerprint hashes; plan baseline/deduplication effects and retain old backups securely. Do not paste tokens, reset links or sensitive logs into public issues.

Retention preview explains the saved policy. Cleanup permanently deletes eligible events, expired report copies/notifications, old closed alerts/notes and old audit records, then records a summary. It does not silently delete open investigations. Review organizational retention and backups before enabling automation. See the privacy document for historical copies and limitations of changing masks.
