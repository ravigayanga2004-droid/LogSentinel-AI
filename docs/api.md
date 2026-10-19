# API reference

Interactive authoritative schemas are at `/api/docs`; OpenAPI JSON is `/api/openapi.json`. All routes below use the `/api` prefix. Responses are JSON except downloads. Validation errors omit submitted values; unexpected errors return a safe error ID. No stack traces or database parameters are exposed.

Browser authentication uses `ls_session` (HTTP-only) and `ls_csrf`. Send the CSRF value in `X-CSRF-Token` for authenticated mutations. Use `X-Workspace-ID` to select one authorized workspace; without it, the API selects an existing membership. Never trust this header without membership validation. API-key ingestion uses `X-API-Key` and cannot read resources.

| Group | Routes |
| --- | --- |
| Health | `GET /health`, `GET /ready` |
| Authentication | `GET /auth/status`, `POST /auth/setup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Recovery/profile | `POST /auth/forgot-password`, `POST /auth/reset-password`, `PATCH /auth/profile`, `POST /auth/password` |
| Workspaces/members | `POST /workspaces`, `GET/POST /members`, `PATCH /members/{id}` |
| Sources | `GET/POST /sources`, `GET/PUT /sources/{id}` |
| Keys | `POST /sources/{id}/keys`, `GET /keys`, `DELETE /keys/{id}` (revocation) |
| Ingestion | `POST /ingest`, `POST /sources/{id}/upload`, `POST /sources/{id}/preview` |
| Jobs | `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/retry` |
| Parsers | `GET /parsers`, `POST /parsers/test` |
| Events | `GET /events`, `GET /events/{id}` (includes related timeline) |
| Saved searches | `GET/POST /saved-searches`, `DELETE /saved-searches/{id}` |
| Rules | `GET/POST /rules`, `GET/PUT /rules/{id}`, `POST /rules/{id}/test` |
| Detection/baselines | `POST /detection/run`, `GET /baselines`, `POST /baselines/{id}/reset` |
| Alerts | `GET /alerts`, `GET/PATCH /alerts/{id}`, `POST /alerts/{id}/notes` |
| Analytics | `GET /analytics` |
| Reports | `GET/POST /reports`, `GET /reports/{id}/download` |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read` |
| Administration | `GET/PUT /settings`, `GET /retention/preview`, `POST /retention/run`, `GET /audit` |

Paginated endpoints return `{items,total,page,page_size}`; use `page_number`, and `page_size` where supported (events/alerts, max 100). Sources, rules, members, keys, parsers, baselines and saved searches are small configuration collections returned as `{items}`; they are not intended as high-volume event stores. Alert results default to the last 168 hours; override `hours` up to 8760.

Event filters: `q`, `source_id`, `severity`, `category`, `event_type`, `service`, `source_host`, `source_ip_hash`, `username_hash`, `status_code`, `parse_status`, `anomaly`, `start`, `end`, `hours`, `sort=asc|desc`. Use UTC ISO timestamps for absolute ranges. Search uses a bound case-insensitive message pattern; SQL wildcard syntax is supported. Saved searches and reports validate their filter keys/types. Analytics supports hours/source/severity/host/service/event type/user/IP and alert-status controls. Source health always describes the last 24 hours; alert aggregates respond to source/severity/status and the selected time window, while entity filters refine event metrics. Export requests state their separate event filter scope.

Creation uses 201, queued work 202, authentication failures 401, denied roles/workspaces 403, absent scoped resources 404, conflicting state 409, oversized input 413, unsupported files 415, validation 422 and limits 429. The rate-limit response includes Retry-After. A liveness success does not imply worker readiness: `/ready` returns 503 when its database/worker checks are unhealthy.

The upload endpoint accepts multipart `file`, JSON `mapping` and boolean `allow_partial`. REST ingestion accepts `{events:[...],idempotency_key?:string}`. Immediate duplicate counts are provisional; authorized operators inspect the completed job result. Machine collectors deliberately cannot fetch job evidence with their write-only key. No outbound integration configuration or action endpoint is exposed.
