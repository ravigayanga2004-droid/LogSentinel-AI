# Testing and verification

Run from the root after installing `requirements.lock`, the editable Python package and `npm ci --prefix frontend`. Use `npm.cmd` in restricted Windows PowerShell. The Python manage wrapper locates `.venv` automatically.

```text
python scripts/manage.py lint
python scripts/manage.py format --check
python scripts/manage.py typecheck
python scripts/manage.py test -q
.venv/Scripts/python scripts/verify_migrations.py
npm run lint
npm run typecheck
npm test
npm run build
npm --prefix frontend run format:check
npm --prefix frontend exec -- playwright install chromium
npm run test:e2e
```

The backend suite covers credentials, role policy, parsing, malformed data, UTC normalization, redaction, safe CSV cells, statistics, full API ingestion/detection/investigation/export workflows, CSRF, Origin validation, reset reuse, session invalidation, key revocation, workspace isolation, retention, lockouts, payload bounds, worker leases, resumable deduplication, baseline reset and a 5,000-record upload. The performance regression verifies bounded pagination and completion within 60 seconds; it is not a production capacity certification.

Unit/integration tests use temporary SQLite databases and staging directories. When `TEST_DATABASE_URL` points to a **dedicated test PostgreSQL database**, every API fixture creates a unique `test_<uuid>` schema, runs the same suite there and drops only that schema afterward. Never point it at an important production database; test users require schema-create/drop privileges. PostgreSQL is required for the deployment path and exercised by CI.

Frontend tests verify theme persistence, text severity labels, accessible feedback, pagination bounds, error retry and API transport. Chromium tests launch disposable backend, worker and frontend servers on 8010/5174. They exercise every major route, both themes, mobile navigation, viewer restrictions, parser privacy, public/recovery pages and the full administrator workflow from workspace creation to report download. Browser captures use synthetic data only; traces/screenshots are generated under ignored artifact folders.

Run browser tests while no bulk formatter or source rewrite is modifying the frontend; Vite hot reload can interrupt an in-progress form. Heavy concurrent Docker compilation can distort response times; perform the final test pass with build activity finished. Tests use accessible role locators for selects and explicit waits for real server outcomes.

`verify_migrations.py` creates a disposable database and checks clean upgrade, schema drift, downgrade and re-upgrade. Its downgrade never touches the development database. Normal application startup does not migrate automatically; Compose has a dedicated migration service.

GitHub Actions defines separate backend and console jobs, SQLite and PostgreSQL suites, formatting/lint/type checks, production build and browser artifacts. A configured workflow is not a claim that a particular GitHub-hosted run has passed; see the final verification record for commands actually executed in this environment. No external paid testing service is required.
