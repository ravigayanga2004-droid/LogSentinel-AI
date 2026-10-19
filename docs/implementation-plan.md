# Implementation plan

## Repository inspection

The initial repository contains one README, one initial commit, and an HTTPS GitHub remote. There is no existing implementation, package manager, or application data to preserve. Local tools: Python 3.14, Node 24, Git and Docker CLI. Use `npm.cmd` on Windows where PowerShell script execution is restricted.

## Decisions

- FastAPI, Pydantic 2 and SQLAlchemy 2 backend; PostgreSQL in deployment, SQLite for a zero-service local quickstart. Alembic owns schema migrations.
- React, TypeScript, Vite, TanStack Query, Recharts and Lucide frontend. Accessible native form controls with server validation; custom design tokens for light/dark themes.
- Durable database job queue with a standalone polling worker, leases, bounded retries and progress. No Redis or paid API is required.
- One-time first-admin setup, Argon2id passwords, hashed opaque sessions, CSRF tokens and per-workspace RBAC. Development seeding is explicit and never runs in production.
- Store redacted events only. Raw-message persistence and outbound integrations are intentionally unavailable; secrets never leave the installation.
- Detection is deterministic and statistical, with versioned explanations. No external AI API and no automated response actions.
- Keep the original README's product intent while replacing it with runnable project documentation.

## Branch and commit workflow

Use real feature branches, focused implementation commits, verification commits and non-fast-forward merges. Target 40–50 total new commits, including merges, without backdating, empty commits, or fabricated contributors. Push feature branches and main when the configured Git credentials permit it.

## Phases

1. `feat/foundation`: project configuration, database/migrations, security primitives, parsers/privacy, baseline math, first unit tests.
2. `feat/platform-api`: authentication, workspace RBAC, source/rule management, search, ingestion pipeline and durable worker.
3. `feat/detection-workflows`: versioned rules, baselines, alert workflow, reports, notifications, retention and API integration tests.
4. `feat/console`: themeable app shell, public/auth pages, dashboard, explorer, investigation workflow, sources/parsers/rules, account/admin pages.
5. `test/system-hardening`: frontend tests, browser workflows, security/regression/performance coverage and fixes found in verification.
6. `chore/release`: Docker/CI, operational documentation, clean migration/seed/deployment checks and final verification record.

After each phase run relevant checks and fix failures. Final verification must report actual results, configuration requirements and unverified constraints; do not claim perfection or production certification.

## Acceptance workflow

Initialize an administrator, create a workspace/source, import logs through the worker, inspect redacted events, run explainable detection, investigate and resolve an alert, export an authorized report, verify viewer restrictions and cross-workspace isolation, test malformed data, deduplication, retention, theme persistence and responsive navigation.

## Execution adjustments

Authentication and the privacy staging module landed with foundation, followed by the remaining platform API/detection/worker workflows together on `feat/platform-api`; a separate detection branch was unnecessary. The console, hardening and release branches preserve the remaining phase boundaries. All commits use actual authorship/time and focused work; no history was backdated or fabricated. Test fixtures caught and corrected a demo-domain validation problem, missing-entity false detections, a SQLite timezone synchronization issue, baseline-reset history leakage and short-identifier digest masking. See final verification for executed checks and constraints.
