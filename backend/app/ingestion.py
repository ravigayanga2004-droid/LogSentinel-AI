import csv
import io
import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Event, Job, Source, Workspace, uid
from app.parsers import ParseError, normalize, parse_line, parse_timestamp
from app.privacy import redact_event
from app.security import entity_hash

STAGING = Path("data/staging")


def prepared_record(line: str | dict, parser: str, masks: list[str], privacy: bool) -> dict:
    canonical = json.dumps(line, sort_keys=True) if isinstance(line, dict) else line.strip()
    fingerprint = entity_hash(canonical)
    try:
        parsed = normalize(line, "json") if isinstance(line, dict) else parse_line(line, parser)
        safe = redact_event(parsed, masks, privacy)
        safe["timestamp"] = parsed["timestamp"].isoformat()
        return {"event": safe, "fingerprint": fingerprint}
    except (ParseError, ValueError, RecursionError):
        return {
            "error": "Record did not match the parser or required schema",
            "fingerprint": fingerprint,
        }


def stage_records(
    records, source: Source, policy: dict, allow_partial: bool = True
) -> tuple[str, dict]:
    STAGING.mkdir(parents=True, exist_ok=True)
    filename = f"{uid()}.jsonl"
    path = STAGING / filename
    summary: dict = {
        "total": 0,
        "accepted": 0,
        "rejected": 0,
        "errors": [],
        "duplicates": 0,
        "redacted_records": 0,
        "time_start": None,
        "time_end": None,
        "parser": source.parser,
    }
    try:
        with path.open("w", encoding="utf-8") as target:
            for number, record in enumerate(records, 1):
                if number > 100000:
                    raise HTTPException(413, "Imports are limited to 100,000 records")
                envelope = prepared_record(
                    record, source.parser, policy.get("masks", []), policy.get("privacy_mode", True)
                )
                envelope["line"] = number
                summary["total"] += 1
                if "error" in envelope:
                    summary["rejected"] += 1
                    if len(summary["errors"]) < 50:
                        summary["errors"].append({"line": number, "message": envelope["error"]})
                else:
                    summary["accepted"] += 1
                    summary["redacted_records"] += 1
                    timestamp = envelope["event"]["timestamp"]
                    summary["time_start"] = min(summary["time_start"] or timestamp, timestamp)
                    summary["time_end"] = max(summary["time_end"] or timestamp, timestamp)
                target.write(json.dumps(envelope, ensure_ascii=True) + "\n")
        if not summary["total"]:
            raise HTTPException(422, "The file contains no records")
        if summary["rejected"] and not allow_partial:
            raise HTTPException(
                422,
                {
                    "message": "Import validation failed. No events were imported. Enable partial import to accept valid rows.",
                    "errors": summary["errors"],
                },
            )
        return filename, summary
    except Exception:
        path.unlink(missing_ok=True)
        raise


def file_records(file, extension: str, mapping: dict):
    text = io.TextIOWrapper(file, encoding="utf-8-sig", errors="strict")
    try:
        if extension == ".csv":
            if not mapping.get("timestamp") or not mapping.get("message"):
                raise HTTPException(422, "CSV requires timestamp and message column mappings")
            reader = csv.DictReader(text)
            if not reader.fieldnames or any(
                value not in reader.fieldnames for value in mapping.values()
            ):
                raise HTTPException(422, "CSV mapping refers to missing columns")
            for row in reader:
                yield {field: row.get(column, "") for field, column in mapping.items()}
        elif extension == ".json":
            value = json.load(text)
            if isinstance(value, dict):
                value = value.get("events", [value])
            if not isinstance(value, list):
                raise HTTPException(422, "JSON must contain an object or event array")
            for row in value:
                yield row if isinstance(row, dict) else "{invalid record"
        else:
            while True:
                line = text.readline(65538)
                if not line:
                    break
                if len(line.encode("utf-8")) > 65536:
                    raise HTTPException(413, "A line exceeds the 64 KiB limit")
                if line.strip():
                    yield line
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error, RecursionError):
        raise HTTPException(422, "File must be valid UTF-8 text with the selected format") from None
    finally:
        text.detach()


def enqueue_ingestion(
    db: Session,
    source: Source,
    actor_id: str | None,
    filename: str,
    summary: dict,
    key: str | None = None,
) -> Job:
    if key:
        old = db.scalar(
            select(Job).where(Job.workspace_id == source.workspace_id, Job.idempotency_key == key)
        )
        if old:
            (STAGING / filename).unlink(missing_ok=True)
            return old
    job = Job(
        workspace_id=source.workspace_id,
        source_id=source.id,
        actor_id=actor_id,
        kind="ingestion",
        payload={"file": filename},
        result=summary,
        idempotency_key=key,
    )
    db.add(job)
    db.flush()
    return job


def ingest_job(db: Session, job: Job):
    source = db.get(Source, job.source_id)
    workspace = db.get(Workspace, job.workspace_id)
    if not source or not source.enabled or not workspace:
        raise ValueError("Source is unavailable or disabled")
    # The path is generated by this service; reject malformed queue payloads defensively.
    filename = job.payload["file"]
    if Path(filename).name != filename or not filename.endswith(".jsonl"):
        raise ValueError("Invalid staging reference")
    window = (workspace.settings or {}).get("duplicate_window_minutes", 60) * 60
    result = dict(job.result)
    cursor = int(result.get("cursor", 0))
    with (STAGING / filename).open(encoding="utf-8") as stream:
        for index, line in enumerate(stream, 1):
            if index <= cursor:
                continue
            envelope = json.loads(line)
            record = envelope.get("event")
            if not record:
                record = {
                    "timestamp": utcnow().isoformat(),
                    "message": "Record could not be parsed; original content discarded",
                    "event_type": "parser_failure",
                    "category": "ingestion",
                    "severity": "medium",
                    "parser_name": source.parser,
                }
                source.last_error_at = utcnow()
            timestamp = parse_timestamp(record.pop("timestamp"))
            bucket = int(timestamp.timestamp()) // window
            existing = db.scalar(
                select(Event).where(
                    Event.source_id == source.id,
                    Event.fingerprint == envelope["fingerprint"],
                    Event.dedup_bucket == bucket,
                )
            )
            if existing:
                existing.duplicates += 1
                result["duplicates"] = result.get("duplicates", 0) + 1
            else:
                details = record.pop("details", {})
                details["line_number"] = envelope["line"]
                details["job_id"] = job.id
                db.add(
                    Event(
                        workspace_id=job.workspace_id,
                        source_id=source.id,
                        timestamp=timestamp,
                        fingerprint=envelope["fingerprint"],
                        dedup_bucket=bucket,
                        details=details,
                        parse_status="failed" if "error" in envelope else "parsed",
                        **record,
                    )
                )
            source.last_event_at = utcnow()
            if "error" not in envelope:
                source.last_parse_at = utcnow()
            result["cursor"] = index
            job.result = dict(result)
            job.progress = min(99, int(index / max(result["total"], 1) * 100))
            if index % 250 == 0:
                from datetime import timedelta

                job.lease_until = utcnow() + timedelta(minutes=10)
                db.commit()
    db.flush()
    # Detection is in the same transaction as completion, making retries safe.
    from app.detection import run_detection

    result["alerts_created"] = run_detection(db, job.workspace_id, source_id=source.id)
    job.result = result
