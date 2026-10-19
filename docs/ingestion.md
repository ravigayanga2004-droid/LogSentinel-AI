# Ingestion

Create an enabled source, choose a parser, then use **Import logs** or a source-scoped API key. Only submit authorized data. Parser testing and upload previews do not create events. Every accepted import receives a durable job ID.

## Files

Allowed extensions: `.log`, `.txt`, `.json`, `.jsonl`, `.csv`. Files must be UTF-8; uploads default to 10 MiB, records to 64 KiB per line, and jobs to 100,000 records. The request envelope has an additional bounded allowance for multipart metadata. The service ignores the client's path and uses its own staging identifier. Uploaded files are never executed or publicly served.

Line formats stream. `.json` accepts an object, an array of event objects, or an `events` array; the bounded JSON file is decoded in memory. JSONL accepts one object per line and preserves logical line numbers. Blank lines are skipped. Parser failures produce safe errors without retaining the original line.

For CSV, map **timestamp** and **message** column names before preview/import. The API accepts additional normalized mapping keys such as `severity` and `source_ip`; the simple UI maps the required two fields. Quoted fields and multiline CSV use the standard CSV reader. CSV rows require a timestamp value. A missing/malformed mapping rejects the import. Invalid rows reject the whole file unless **Allow partial import** is explicitly selected. With partial import, valid events and safe parser-failure records are stored; original invalid content is discarded.

Upload progress measures transport; job progress measures database processing. The source jobs table reports total, valid, failed, duplicate and privacy-processed records, errors with line numbers, and detection results. The job response also includes detected time range and parser. `redacted_records` counts records processed by the privacy layer, not individual substituted fields.

## REST batches

An administrator/source administrator creates a key on one enabled source. Copy it once; only its hash and prefix persist. The key cannot search or read data. Revocation takes effect immediately. The endpoint allows 60 requests per key per minute and up to 1,000 events per batch.

```bash
curl http://localhost:8000/api/ingest \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $LOGSENTINEL_INGEST_KEY" \
  --data '{"idempotency_key":"collector-batch-001","events":[{"timestamp":"2026-10-19T04:00:00Z","message":"Synthetic failed authentication","event_type":"login_failed","category":"authentication","username":"synthetic-user","ip":"192.0.2.10","service":"sshd"}]}'
```

Use HTTPS outside local development. Do not put a real key in source code, shell history, screenshots or issues. The immediate response includes accepted/rejected counts and a job ID. Duplicate counts become authoritative after worker processing. Use a fresh idempotency key for a new batch; reusing a key returns the previous job even if a caller changes the content. Keys are scoped by source within the workspace. File uploads support the `Idempotency-Key` header.

## Persistence and retries

Normalized envelopes are redacted before staging. The worker writes batches of 250, stores the cursor in the same transaction, and resumes safely after a crash. Fingerprints use HMAC over canonical input; a source/fingerprint/time-bucket constraint prevents duplicate rows. Duplicate records increase a visible counter and do not silently disappear. The configurable deduplication window is a UTC epoch-aligned bucket, so identical records across a bucket boundary can be retained separately.

Completed staging files are removed. Failed files remain redacted and available for retry. Review failed jobs, correct source configuration, then use Retry. No raw-data archive or local collector is included. To collect continuously, configure your own authorized sender to submit bounded JSON batches using its source key.
