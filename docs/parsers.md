# Parser framework

`parse_line` is the versioned common interface. It returns normalized fields or a safe `ParseError`; records are never executed. Parsers have version 1.0. Testing returns a format-match indicator or generic-fallback label, redacted field preview and line-level errors. The test endpoint limits input to 64 KiB and the first 100 lines. File previews inspect at most 20 records, without import.

| Parser | Input and behavior |
| --- | --- |
| `auto` | Tries structured JSON, web access, auth/syslog and key-value patterns before generic fallback |
| `json` | Object with `message`/`msg`, optional ISO/epoch timestamp and normalized security/web fields |
| `linux_auth` | Syslog/ISO host/process lines; extracts failed/accepted SSH password/public-key activity |
| `nginx` / `apache` | Common/combined-style access line: address, time, method/path and HTTP status |
| `key_value` | Quoted key/value tokens using safe `shlex` tokenization, never shell execution |
| `generic` | Human-readable application message, optional ISO prefix and conventional severity label |
| `windows` | Basic JSON exports with `Message`, `TimeCreated`, `EventID`; XML/EVTX is not supported |

An explicit parser rejects lines that do not match. Auto's generic fallback may accept an unfamiliar line as an unclassified log; use an explicit parser when strict format validation is required. JSON with a recognized opening brace and invalid syntax is reported as an error rather than silently falling back. HTTP status codes must be 100–599. Missing messages are errors. Timezone-less ISO timestamps are interpreted as UTC; syslog timestamps infer the current year and handle December/January rollover. Sources without a timestamp use receipt time, so historical analysis requires a timestamp-bearing format. Generic Linux auth and raw generic messages do not provide every optional field automatically.

Severity normalizes fatal/emergency to critical, error to high, warning to medium, debug to low, and unknown values to informational (`info`). Structured logs can explicitly provide category, event type, outcome, user/source, service, path/status and optional metadata. Frequently queried fields become columns; additional bounded fields live in redacted details. Source addresses and usernames become hashes before storage; URL queries/fragments are stripped.

Example synthetic SSH input:

```text
Oct 19 04:00:00 auth-prod-01 sshd[123]: Failed password for invalid user demo-user from 192.0.2.10 port 22 ssh2
```

Example synthetic application input:

```json
{"timestamp":"2026-10-19T04:00:00Z","message":"Request completed","status_code":403,"path":"/admin?token=redact-me","ip":"192.0.2.10","service":"nginx"}
```

Add a parser by implementing bounded extraction, timestamp normalization and safe field errors, then add malformed-input, redaction and normalization tests. Bump the parser version when semantics change. Never add arbitrary code evaluation or user-supplied regex execution.
