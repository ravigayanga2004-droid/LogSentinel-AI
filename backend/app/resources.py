import json
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy import func, select

from app.common import Context, require_workspace_access, serialize
from app.config import get_settings
from app.db import aware, utcnow
from app.ingestion import enqueue_ingestion, file_records, stage_records
from app.models import APIKey, Baseline, Event, Job, SavedSearch, Source
from app.parsers import PARSERS, ParseError, parse_line
from app.privacy import redact_event, redact_sensitive_fields
from app.schemas import NameInput, ParserInput, SearchInput, SourceInput
from app.security import digest, token

router = APIRouter(prefix="/api", tags=["Sources and events"])


def page(db, query, page_number=1, page_size=25):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.offset((page_number - 1) * page_size).limit(page_size))
    return {"items": [serialize(row) for row in rows], "total": total, "page": page_number, "page_size": page_size}


def source_health(db, source):
    since = utcnow() - timedelta(hours=24)
    total = db.scalar(select(func.count()).select_from(Event).where(Event.source_id == source.id, Event.timestamp >= since)) or 0
    failures = db.scalar(select(func.count()).select_from(Event).where(Event.source_id == source.id, Event.timestamp >= since, Event.parse_status == "failed")) or 0
    silent = not source.last_event_at or aware(source.last_event_at) < utcnow() - timedelta(minutes=source.silence_minutes)
    state = "disabled" if not source.enabled else "silent" if silent else "degraded" if failures / max(total, 1) > 0.1 else "healthy"
    latency = db.scalar(select(func.avg(func.julianday(Event.received_at) - func.julianday(Event.timestamp))).where(Event.source_id == source.id)) if db.bind.dialect.name == "sqlite" else None
    return {**serialize(source), "health": state, "health_score": 0 if state in {"disabled", "silent"} else max(0, round(100 - failures / max(total, 1) * 100)), "event_count": total, "parse_failures": failures, "events_per_minute": round(total / 1440, 2), "average_latency_seconds": round(max(0, (latency or 0) * 86400), 2)}


@router.get("/sources")
def sources(ctx: Context = Depends(require_workspace_access)):
    return {"items": [source_health(ctx.db, source) for source in ctx.db.scalars(select(Source).where(Source.workspace_id == ctx.wid).order_by(Source.name))]}


@router.post("/sources", status_code=201)
def add_source(data: SourceInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("sources")
    source = Source(workspace_id=ctx.wid, **data.model_dump())
    ctx.db.add(source)
    ctx.db.flush()
    ctx.audit("source.created", "source", source.id)
    return serialize(source)


@router.get("/sources/{source_id}")
def get_source(source_id: str, ctx: Context = Depends(require_workspace_access)):
    return source_health(ctx.db, ctx.get(Source, source_id))


@router.put("/sources/{source_id}")
def edit_source(source_id: str, data: SourceInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("sources")
    source = ctx.get(Source, source_id)
    for key, value in data.model_dump().items():
        setattr(source, key, value)
    ctx.audit("source.updated", "source", source.id)
    return serialize(source)


@router.get("/parsers")
def parsers(ctx: Context = Depends(require_workspace_access)):
    return {"items": [{"name": name, "version": "1.0"} for name in PARSERS]}


@router.post("/parsers/test")
def test_parser(data: ParserInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("ingest")
    results = []
    for number, line in enumerate(data.text.splitlines()[:100], 1):
        if not line.strip():
            continue
        try:
            result = redact_event(parse_line(line, data.parser), ctx.workspace.settings.get("masks", []))
            results.append({"line": number, "parsed": True, "match": "generic fallback" if result["parser_name"] == "generic" else "format match", "event": result})
        except ParseError as exc:
            results.append({"line": number, "parsed": False, "error": str(exc)})
    return {"test_only": True, "items": results}


@router.post("/sources/{source_id}/keys", status_code=201)
def create_key(source_id: str, data: NameInput, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("sources")
    source = ctx.get(Source, source_id)
    raw = "ls_" + token()
    key = APIKey(workspace_id=ctx.wid, source_id=source.id, name=data.name, token_hash=digest(raw), prefix=raw[:10])
    ctx.db.add(key)
    ctx.db.flush()
    ctx.audit("api_key.created", "api_key", key.id)
    return {**serialize(key), "key": raw, "message": "Copy this key now. It will not be displayed again."}


@router.get("/keys")
def keys(ctx: Context = Depends(require_workspace_access)):
    ctx.permit("sources")
    return {"items": [serialize(key) for key in ctx.db.scalars(select(APIKey).where(APIKey.workspace_id == ctx.wid))]}


@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("sources")
    key = ctx.get(APIKey, key_id)
    key.revoked = True
    ctx.audit("api_key.revoked", "api_key", key.id)
    return {"ok": True}


@router.post("/sources/{source_id}/upload", status_code=202)
def upload(source_id: str, file: UploadFile = File(...), mapping: str = Form("{}"), allow_partial: bool = Form(False), idempotency_key: str | None = Header(None), ctx: Context = Depends(require_workspace_access)):
    ctx.permit("ingest")
    source = ctx.get(Source, source_id)
    if not source.enabled:
        raise HTTPException(409, "Enable the source before importing")
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".log", ".txt", ".json", ".jsonl", ".csv"}:
        raise HTTPException(415, "Choose .log, .txt, .json, .jsonl or .csv")
    if file.size is None or file.size > get_settings().upload_max_bytes:
        raise HTTPException(413, "File exceeds the upload size limit")
    if idempotency_key and len(idempotency_key) > 100:
        raise HTTPException(422, "Idempotency key is too long")
    try:
        columns = json.loads(mapping)
        if not isinstance(columns, dict) or len(columns) > 30 or not all(isinstance(k, str) and isinstance(v, str) for k, v in columns.items()):
            raise ValueError
    except ValueError:
        raise HTTPException(422, "CSV mapping must be a JSON object of column names") from None
    filename, summary = stage_records(file_records(file.file, extension, columns), source, ctx.workspace.settings, allow_partial)
    job = enqueue_ingestion(ctx.db, source, ctx.user.id, filename, summary, f"{source.id}:{idempotency_key}" if idempotency_key else None)
    ctx.audit("ingestion.queued", "job", job.id)
    return serialize(job)


@router.get("/jobs")
def jobs(page_number: int = Query(1, ge=1), ctx: Context = Depends(require_workspace_access)):
    ctx.permit("ingest")
    return page(ctx.db, select(Job).where(Job.workspace_id == ctx.wid).order_by(Job.created_at.desc()), page_number)


@router.get("/jobs/{job_id}")
def job_status(job_id: str, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("ingest")
    return serialize(ctx.get(Job, job_id))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, ctx: Context = Depends(require_workspace_access)):
    ctx.permit("ingest")
    job = ctx.get(Job, job_id)
    if job.status != "failed":
        raise HTTPException(409, "Only failed jobs may be retried")
    job.status, job.attempts, job.error, job.available_at = "queued", 0, None, utcnow()
    ctx.audit("job.retried", "job", job.id)
    return serialize(job)


def event_query(wid: str, filters: dict):
    query = select(Event).where(Event.workspace_id == wid)
    allowed = {"q", "source_id", "severity", "category", "event_type", "service", "source_host", "source_ip_hash", "username_hash", "status_code", "parse_status", "anomaly", "start", "end", "hours"}
    if set(filters) - allowed:
        raise HTTPException(422, "Unknown event filter")
    for key in allowed - {"q", "start", "end", "anomaly", "hours"}:
        if filters.get(key) not in {None, ""}:
            query = query.where(getattr(Event, key) == filters[key])
    if filters.get("q"):
        query = query.where(Event.message.ilike(f"%{str(filters['q'])[:200]}%", escape="\\"))
    from app.parsers import parse_timestamp
    try:
        if filters.get("start"):
            query = query.where(Event.timestamp >= parse_timestamp(filters["start"]))
        elif filters.get("hours"):
            hours = float(filters["hours"])
            if not 0 < hours <= 8760:
                raise ValueError
            query = query.where(Event.timestamp >= utcnow() - timedelta(hours=hours))
        if filters.get("end"):
            query = query.where(Event.timestamp <= parse_timestamp(filters["end"]))
    except (ValueError, OverflowError):
        raise HTTPException(422, "Invalid date range") from None
    if filters.get("anomaly"):
        query = query.where(Event.anomaly_score > 0)
    return query


@router.get("/events")
def events(q: str = Query("", max_length=200), source_id: str = "", severity: str = "", category: str = "", event_type: str = "", service: str = "", source_host: str = "", source_ip_hash: str = "", username_hash: str = "", status_code: int | None = None, parse_status: str = "", anomaly: bool = False, start: str = "", end: str = "", hours: float | None = None, page_number: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), sort: str = Query("desc", pattern="^(asc|desc)$"), ctx: Context = Depends(require_workspace_access)):
    filters = {key: value for key, value in locals().items() if key in {"q", "source_id", "severity", "category", "event_type", "service", "source_host", "source_ip_hash", "username_hash", "status_code", "parse_status", "anomaly", "start", "end", "hours"} and value is not None}
    query = event_query(ctx.wid, filters).order_by(Event.timestamp.asc() if sort == "asc" else Event.timestamp.desc(), Event.id)
    return page(ctx.db, query, page_number, page_size)


@router.get("/events/{event_id}")
def event_detail(event_id: str, ctx: Context = Depends(require_workspace_access)):
    event = ctx.get(Event, event_id)
    from sqlalchemy import or_
    related = select(Event).where(Event.workspace_id == ctx.wid, Event.source_id == event.source_id, Event.timestamp >= aware(event.timestamp) - timedelta(minutes=15), Event.timestamp <= aware(event.timestamp) + timedelta(minutes=15), Event.id != event.id, or_(Event.source_ip_hash == event.source_ip_hash if event.source_ip_hash else False, Event.username_hash == event.username_hash if event.username_hash else False)).order_by(Event.timestamp).limit(100)
    return {**serialize(event), "related": [serialize(row) for row in ctx.db.scalars(related)]}


@router.get("/saved-searches")
def saved_searches(ctx: Context = Depends(require_workspace_access)):
    return {"items": [serialize(row) for row in ctx.db.scalars(select(SavedSearch).where(SavedSearch.workspace_id == ctx.wid, SavedSearch.user_id == ctx.user.id))]}


@router.post("/saved-searches", status_code=201)
def save_search(data: SearchInput, ctx: Context = Depends(require_workspace_access)):
    event_query(ctx.wid, data.filters)
    search = SavedSearch(workspace_id=ctx.wid, user_id=ctx.user.id, name=data.name, filters=redact_sensitive_fields(data.filters))
    ctx.db.add(search)
    ctx.db.flush()
    return serialize(search)


@router.delete("/saved-searches/{search_id}")
def delete_search(search_id: str, ctx: Context = Depends(require_workspace_access)):
    search = ctx.get(SavedSearch, search_id)
    if search.user_id != ctx.user.id:
        raise HTTPException(404, "Saved search not found")
    ctx.db.delete(search)
    return {"ok": True}


@router.get("/baselines")
def baselines(ctx: Context = Depends(require_workspace_access)):
    return {"items": [serialize(row) for row in ctx.db.scalars(select(Baseline).where(Baseline.workspace_id == ctx.wid))]}
