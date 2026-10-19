# Deployment

## Local containers

```text
python scripts/init_env.py --docker
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
```

The generated file contains fresh URL-safe secrets, sets the browser origin to `http://localhost:8080`, and is Git-ignored. Compose requires `POSTGRES_PASSWORD` and `SECRET_KEY`; it never embeds production credentials in the repository. The database is not published to the host; Nginx binds `127.0.0.1:8080`. Optional `WEB_PORT` changes that host port; update PUBLIC_ORIGIN to match.

The one-shot `migrate` container waits for PostgreSQL and runs `alembic upgrade head`. API/worker wait for successful migration. A shared job volume persists redacted staging; the PostgreSQL volume persists all account/evidence/configuration data. Backend/worker run as UID 10001 and Nginx uses an unprivileged image. Containers use health checks, bounded retries, restart policies and no-new-privileges where applicable.

`/api/health` is process liveness. `/api/ready` checks database access and a worker heartbeat newer than 90 seconds. Monitor both. Readiness can be briefly degraded during initial startup. Start with one worker and at least 2 CPU cores / 2–4 GiB RAM for a small deployment; measure real workloads before committing to an SLO. No Redis dependency is present.

## Production configuration

Use a fresh database and complete first-administrator setup over a restricted connection. Do not deploy the synthetic demo database. Before exposing the service:

1. Configure a stable random SECRET_KEY of at least 32 characters and a separate URL-safe database password. Protect the environment file or inject secrets through your deployment's secret manager.
2. Set `ENVIRONMENT=production`, `COOKIE_SECURE=true` and `PUBLIC_ORIGIN=https://your-exact-hostname`.
3. Terminate HTTPS through an operator-managed reverse proxy/load balancer. Forward the same public host to the localhost-bound console. Ensure HTTP redirects to HTTPS; avoid logging recovery URL queries.
4. Keep API, database and worker networks private. Restrict initial setup, database access, filesystem access and backups. Configure disk encryption and encrypted backup storage.
5. Review roles, source boundaries, redaction masks, export policy and retention. Automatic retention starts disabled.
6. Configure optional SMTP only if recovery email is needed. Otherwise use the verified operator CLI.
7. Run migrations, tests, health checks and a restore drill before onboarding important logs.

The backend refuses production startup with SQLite, insecure cookies, a non-HTTPS public origin or a missing/placeholder secret. This does not replace a deployment security review. TLS issuance, DNS, ingress/WAF policy, secret rotation and external monitoring remain operator responsibilities.

## Updating

Back up first. Build immutable images from a reviewed commit, run migration once, then restart API/worker/frontend. Dependencies are installed in a separate cached Docker layer before application source is copied. Registry/package network access is needed for an uncached build. Source-only changes reuse the pinned dependency layer. No deployment performs an automatic schema downgrade.

```text
docker compose --env-file .env.docker build
docker compose --env-file .env.docker run --rm migrate
docker compose --env-file .env.docker up -d
```

Inspect readiness and test a small authorized import. Revert application images only when schema compatibility has been reviewed. Never use volume-removal commands as an upgrade or troubleshooting step. See operations for backup, restore and queue recovery.
