# Explainable detection engine

The engine observes authorized submitted logs. It does not establish malicious intent or take response actions. Detections require local tuning and adequate, accurate data.

## Rules

Sixteen versioned kinds are available: `failed_login`, `success_after_failures`, `http_401`, `http_403`, `error_spike`, `volume_spike`, `sensitive_path`, `new_entity`, `many_users`, `many_sources`, `unusual_process`, `source_silence`, `parser_failure`, `out_of_hours`, `severity_spike`, `statistical`.

Rules carry a name, description, enabled state, severity, integer threshold, window, cooldown, grouping field, config, author and version. Saving creates a new version. The test operation evaluates existing evidence without creating alerts. Manual runs enqueue a job; periodic worker maintenance schedules evaluation approximately every minute. Imports also evaluate their source after ingestion. Source silence can therefore be detected without new arrivals.

Group by source-IP hash, username hash, service or source ID. Evaluations are per source. User/source-count rules skip missing entity identifiers. New-entity detections require prior source history and absence of that group in earlier history; rarity alone is not classified as malicious. Failed-login/success sequence requires enough preceding failures within the configured window before a success. Parser-failure counts include repeated invalid records even when their storage is deduplicated; normal duplicate records do not inflate other rule counts.

Optional configuration is a validated JSON object:

```json
{"source_ids":["source-uuid"],"service":"sshd","excluded_ip_hashes":[],"excluded_user_hashes":[],"paths":["/admin","/internal"],"expected_processes":["sshd","nginx"],"start_hour":6,"end_hour":22}
```

Lists are bounded and paths use literal prefix matching. No arbitrary code or regex is accepted. Start/end hours use UTC, with an increasing same-day interval. Source silence uses the larger of the rule's threshold and source's configured silence minutes. Statistical windows are fixed at five minutes; other rules use their configured window. Other than source silence, thresholds count matching events or distinct entities. Error/severity spike rules use threshold counts; request-volume rules use an absolute event threshold, complemented by the statistical detector.

## Statistical baseline

Per-source five-minute counts use up to 24 hours of history, excluding the active five-minute window. Empty windows between the first historical event and the current cutoff count as zero. At least 12 historical windows are required before trust. Metrics include rolling mean, median, median absolute deviation (MAD), standard deviation, p95 and EWMA (alpha 0.3).

The trigger threshold is the maximum of 5, median + 6 × max(MAD, 1), mean + 3 × standard deviation, and the rule's configured minimum threshold. The result records observed value, expected median, threshold, robust z-score, ordinary z-score and confidence. Confidence and severity remain separate. p95/EWMA are descriptive baseline metrics; they do not independently create alerts. Baseline reset increments the version and excludes all pre-reset history until new data is sufficient.

No seasonal model or Isolation Forest is included. Baselines are per source; service scoping is available on rules, but independent per-service statistical models would require a future feature extension. No IP geolocation, device fingerprint enrichment or causal config-change sequence model is inferred from absent data.

## Alert generation

Alerts include the trigger condition, observed count, threshold, window, source, entity hash, confidence limitation, rule version and recommended investigation steps. At most 100 chronological evidence references attach to an alert; the count can be larger. Cooldown and expiring suppression prevent repeated observations from flooding the queue. A unique dedup key protects concurrent retries. Resolved/false-positive alerts can recur after cooldown when fresh activity still matches; expiry of suppression resumes evaluation. The initial explanation is preserved rather than silently rewritten by an AI service.

The engine streams matching event queries in bounded fetches. Very high-cardinality workspaces can still require substantial group memory and rule-query time. Start with one worker, monitor queue age and review query plans before scaling. Recommended future work: incremental feature buckets, partitioning, per-service/seasonal baselines and tuned long-duration performance SLOs.
