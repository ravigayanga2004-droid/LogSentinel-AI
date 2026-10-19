# Security model

## Identity and access

Passwords use Argon2id with a 64 MiB memory cost and three iterations. Opaque session values are random; only SHA-256 digests are stored. Sessions expire after 12 hours by default and are checked server-side on every request. Session cookies are HTTP-only, SameSite=Lax and Secure in production. A separate random CSRF token is required for authenticated mutations. An exact Origin check also covers public authentication mutations when the browser sends Origin.

Login counters are shared in the database: eight attempts per account and 30 per source address over 15 minutes. Unknown accounts receive the same credential error and a dummy password-hash verification. Recovery returns a generic response, uses hashed single-use 30-minute tokens, and invalidates all sessions. Password changes require the current password. Recovery email is sent only through explicitly configured SMTP. Otherwise the verified installation operator uses the local CLI.

Initial setup is available only before any account exists, with an atomic singleton lock. Restrict network access until setup is complete. Public registration stays disabled. A workspace always retains at least one administrator. The local `grant-member` CLI supports verified existing-account membership without letting an administrator seize an account's password.

| Role | Read | Investigate | Ingest | Sources/keys | Rules | Export | Users/policy/audit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Administrator | yes | yes | yes | yes | yes | yes | yes |
| Analyst | yes | yes | yes | no | yes | yes | no |
| Viewer | yes | no | no | no | no | no | no |
| Source administrator | yes | no | yes | yes | no | no | no |

Workspace members can read all sources in that workspace. Source-specific read ACLs are not implemented; use separate workspaces when different readers need different data. Resource lookups include workspace scope. API keys are revocable, source-bound write-only credentials.

## Input, output and secrets

Inputs are never executed; parsers use bounded regular expressions, JSON/CSV decoding and literal configured masks. SQLAlchemy binds parameters. React escapes text; no HTML injection rendering is used. Arbitrary regex rules, outbound URL fetches and webhooks are unavailable, removing an SSRF surface. Uploads require an allowed extension, UTF-8 content, size bounds and record validation; the file is never served as executable content. Content-Type alone is not trusted as proof of file validity.

Secret keys, session values, reset tokens and API keys must not enter Git. API keys appear only once at creation. Pydantic errors omit submitted values. API and worker logs emit allowlisted structured metadata, never raw records or exception strings. Recovery URL access logging is disabled at Nginx. CSV cells that could become formulas are escaped. Download authorization and current export policy are rechecked.

The Nginx configuration sets CSP, frame denial, nosniff, no-referrer and browser capability restrictions. The API disables caching and production emits HSTS. HTTPS termination belongs to the operator. Keep the database/API off public interfaces; the Compose entry point binds localhost.

## Threat-model limits

The application does not claim immunity to every attack. There is no MFA/SSO, external penetration-test certification, encrypted-at-application-layer event store, tamper-evident audit chain or field-level read ACL. Use encrypted disks/backups and restricted database access. SMTP delivery depends on the relay; email timing can differ from nonexistent accounts even though the response is generic. The reset-token route remains bounded by request limits, but deployment-level request throttling is recommended.

Production configuration refuses missing/placeholder secrets, insecure cookies, a non-HTTPS origin or a SQLite URL. Treat any exposed credential as compromised; revoke sessions/keys and follow the incident process. See privacy and operations documents for data handling and backups.
