# Final verification — 19 October 2026

## Implemented and exercised

LogSentinel AI includes persistent workspace accounts, four server-enforced roles, first-administrator setup, Argon2id login, hashed sessions, CSRF, logout, password changes/recovery, source-scoped API keys, redaction, normalized log ingestion, parser previews, resumable jobs, duplicate accounting, event search/saved views, versioned rules, statistical baselines, alert investigations, assignment/notes/evidence/tags/status/suppression, notifications, analytics, CSV/JSON reports, retention previews/cleanup, audit history, responsive layouts, and persistent light/dark themes.

The repository started with one README and one commit. Work proceeded through foundation, platform API, console, system hardening and release branches, with focused commits and merges. The original product purpose is preserved. No authors, dates or historical activity were fabricated. The published feature-branch history is retained; final validation changes are committed on top before merging to main.

## Commands and results

| Verification | Actual result |
| --- | --- |
| `python -m pytest -q --tb=short` on local SQLite | **70 passed**, final complete run 62.44 s |
| Same backend suite against dedicated PostgreSQL 17 test database, isolated schemas | **70 passed**, 52.66 s |
| PostgreSQL ingestion → detection → investigation → report download regression | Passed after fixing Decimal JSON serialization |
| `npm --prefix frontend test` | **13 passed**, including stale/valid workspace selection |
| `npm --prefix frontend run test:e2e` | **5 Chromium workflows passed** |
| Responsive/theme/all-routes workflow after mobile filter adjustment | **1 passed**, 48.8 s with 13 route visits and two viewport sizes |
| `ruff check backend scripts` | Passed |
| `ruff format --check backend scripts` | Passed |
| `mypy backend/app` | Passed, 21 source modules |
| Frontend ESLint and TypeScript | Passed |
| Frontend Prettier check | Passed |
| `npm --prefix frontend run build` | Passed; separate application, React, query and chart chunks |
| `alembic upgrade head` and `alembic check` | Passed; no schema drift |
| `python scripts/verify_migrations.py` | Clean upgrade, check, downgrade and re-upgrade passed in a disposable database |
| Docker Compose configuration and initial clean PostgreSQL migration | Passed |
| Database, API, worker and frontend container health | Passed; frontend probe uses explicit IPv4 loopback |
| `/api/ready` through Nginx | HTTP 200; database and worker reported ready |
| Chromium against the actual built Nginx production bundle | Login, live dashboard, theme switching, saved-search creation and confirmed deletion passed; no browser exceptions |
| Live Compose PostgreSQL smoke | REST ingestion, idempotency, worker detection, redaction, evidence notes, resolution, JSON report download, malformed-line recovery and temporary-key revocation passed |
| `python scripts/verify_secrets.py` | No tracked local deployment secrets or private-key/token signatures found |
| `git diff --check` | Passed |

PostgreSQL tests ran in a dedicated `logsentinel_test` database and created/dropped only fixture-owned `test_<uuid>` schemas. Browser tests used their own temporary SQLite database and staging directory. They never reset the development or Compose application database.

## Browser and security evidence

Chromium exercised administrator login; workspace creation/isolation; source creation; redacted file preview/import; worker completion; event evidence; failed-login detection; note creation; resolution; authorized report download; viewer restrictions; parser failure/redaction; public privacy/terms/recovery pages; theme persistence; mobile navigation; and all primary routes. Screenshots contain synthetic fixtures only:

- [Dark dashboard](screenshots/dashboard-dark.png)
- [Light dashboard](screenshots/dashboard-light.png)
- [Mobile event explorer](screenshots/explorer-mobile.png)

Backend regressions cover role restrictions, cross-workspace source/rule/report access, session invalidation, reset-token reuse, CSRF, Origin validation, login lockout, API-key revocation, malicious extension rejection, oversized request/file rejection, malformed lines, CSV mapping/partial-import semantics, redaction, formula-safe CSV, idempotency, duplicate jobs/events/alerts, active and expired worker leases, source silence, parser-failure counts, baseline resets, report policy enforcement and retention audit summaries.

A 5,000-record import test checks completion, exact retained count and page 50 of 100-record results. The strict 60-second import gate passed with build contention removed. A run performed during heavy Docker compilation exceeded the timing gate while retaining all records correctly; frontend process-start timeouts were also observed under that load. Tests now use one frontend worker. These checks do not establish a production throughput or latency guarantee.

The final Compose rebuild includes the validated source tree. All four persistent services reported healthy; the console returned HTTP 200 with its CSP header. Synthetic demo data is available at `http://localhost:8080`. Public development credentials are documented in README; they must not be carried into production. The live smoke added clearly labeled synthetic verification evidence and revoked its temporary ingestion credential afterward.

Verification found and fixed a SQLite timezone synchronization issue, invalid demo email domain, missing-entity false detections, baseline history surviving reset, short-username masking corrupting hashes, PostgreSQL Decimal report serialization, demo seeding competing with a live worker, and a localhost/IPv6 container health probe mismatch. Demo imports now hold leases while the seeder processes them. The queue recovered the observed concurrent demo import, and existing data was preserved.

## Configuration and practical limits

- Local development uses a generated, Git-ignored `.env`; Compose uses a separately generated `.env.docker`. The stable secret is required for consistent hashes across processes.
- Production requires PostgreSQL, HTTPS, Secure cookies, a fresh long random secret, private service networks, protected volumes and a reviewed backup/retention policy. The demonstrated Compose deployment is local HTTP development mode.
- SMTP was not configured or sent to an external service; recovery through a locally generated one-time link is implemented and token consumption is tested. Operator-supplied SMTP credentials, TLS issuance and public DNS remain deployment configuration.
- Raw-message storage, external AI summaries, arbitrary webhooks/URL fetching, local collectors, PDF exports, EVTX/XML parsing, geolocation inference, MFA/SSO, seasonal/Isolation Forest models, event partitioning and multi-region orchestration are not included. They are optional/future capabilities rather than nonfunctional controls.
- Uploads default to 10 MiB / 100,000 records; REST batches to 1,000 events; search pages to 100; reports to 10,000 event rows. JSON arrays are decoded within the bounded file size. Line formats stream. Upload validation/parsing/redaction is synchronous and bounded; persistence/detection/report generation is asynchronous.
- Rules can scope by source/service, but statistical baselines are per source. Out-of-hours rules use UTC. Fixed role permissions replace editable permission tables. Workspace membership authorizes reading all sources inside that workspace; use separate workspaces for narrower access boundaries.
- Report event filters apply to evidence; JSON includes separately described workspace alert/note context with explicit limits. Changing redaction masks does not rewrite already-stored messages. Redaction is heuristic and requires source-specific review.
- Completed redacted staging files are removed; failed/unreferenced files require operator review. There is no automatic orphan-file garbage collector. Default event retention also expires report copies and notifications; open alerts can outlive their expired event evidence.
- One Starlette/TestClient deprecation warning remains for HTTPX test transport. It does not fail the verified tests. Migrate the test transport when the supported FastAPI/Starlette combination requires it.
- A complete external penetration test, long-duration load campaign, live SMTP relay test, production HTTPS deployment, backup/restore drill and GitHub-hosted CI-run status were not independently certified here. CI and operational procedures are supplied; do not infer those external results from local checks.

## Recommended next operational work

Use a fresh production database rather than public demo accounts. Configure TLS and backup storage, conduct a restore drill, review data-collection authorization and masks, tune thresholds with real authorized data, monitor queue age/source silence, and measure capacity before increasing retention or worker concurrency. Add MFA/SSO, partitioning and incremental feature aggregation if organizational scale requires them. No detection automatically blocks users or modifies monitored systems.
