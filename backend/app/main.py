import json
import logging
import time
import uuid
from datetime import timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import admin, analytics, auth, resources, workflows
from app.common import create_audit_log, serialize
from app.config import get_settings
from app.db import get_db, utcnow
from app.ingestion import enqueue_ingestion, stage_records
from app.models import APIKey, Source, WorkerHeartbeat, Workspace
from app.schemas import BatchInput
from app.security import digest, rate_limit

logger = logging.getLogger("logsentinel.api")
logging.basicConfig(level=logging.INFO, format="%(message)s")
app = FastAPI(title="LogSentinel AI", version="1.0.0", description="Authorized, privacy-conscious defensive monitoring. Anomalies are observations, not proof of malicious intent.", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


class RequestBoundary:
    def __init__(self, wrapped):
        self.app = wrapped

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        settings = get_settings()
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("latin1")
        limit = settings.upload_max_bytes + 1024 * 1024
        try:
            content_length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            content_length = limit + 1
        if content_length > limit:
            return await JSONResponse({"detail": "Request exceeds the upload limit"}, status_code=413)(scope, receive, send)
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"} and origin and origin != settings.public_origin:
            return await JSONResponse({"detail": "Untrusted request origin"}, status_code=403)(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > limit:
                raise HTTPException(413, "Request exceeds the upload limit")
            return message

        await self.app(scope, bounded_receive, send)


app.add_middleware(RequestBoundary)


@app.middleware("http")
async def response_security(request: Request, call_next):
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.error(json.dumps({"event": "request.failed", "request_id": request_id}))
        response = JSONResponse({"detail": "An unexpected error occurred", "error_id": request_id}, status_code=500)
    response.headers.update({"X-Request-ID": request_id, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store", "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
    if get_settings().environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info(json.dumps({"event": "request.completed", "method": request.method, "status": response.status_code, "request_id": request_id, "duration_ms": round((time.monotonic() - started) * 1000)}))
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Pydantic includes the supplied input by default; never echo passwords, tokens or logs.
    return JSONResponse({"detail": [{"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]} for error in exc.errors()]}, status_code=422)


@app.exception_handler(IntegrityError)
async def conflict_error(request: Request, exc: IntegrityError):
    return JSONResponse({"detail": "This operation conflicts with an existing record. Refresh and try again."}, status_code=409)


for router in (auth.router, resources.router, workflows.router, analytics.router, admin.router):
    app.include_router(router)


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/ready", tags=["Health"])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        worker = db.scalar(select(func.count()).select_from(WorkerHeartbeat).where(WorkerHeartbeat.last_seen >= utcnow() - timedelta(seconds=90))) or 0
        if not worker:
            return JSONResponse({"status": "degraded", "database": "ok", "worker": "unavailable"}, status_code=503)
        return {"status": "ready", "database": "ok", "worker": "ok"}
    except SQLAlchemyError:
        return JSONResponse({"status": "unavailable"}, status_code=503)


@app.post("/api/ingest", status_code=202, tags=["Machine ingestion"])
def ingest_batch(data: BatchInput, x_api_key: str = Header(""), db: Session = Depends(get_db)):
    key = db.scalar(select(APIKey).where(APIKey.token_hash == digest(x_api_key), APIKey.revoked.is_(False)))
    if not key:
        raise HTTPException(401, "Invalid ingestion credentials")
    rate_limit(db, f"ingestion:{key.id}", 60, 60)
    source = db.get(Source, key.source_id)
    if not source or not source.enabled or source.workspace_id != key.workspace_id:
        raise HTTPException(403, "Log source is unavailable")
    workspace = db.get(Workspace, key.workspace_id)
    filename, summary = stage_records(iter(data.events), source, workspace.settings, allow_partial=True)
    job = enqueue_ingestion(db, source, None, filename, summary, f"{source.id}:{data.idempotency_key}" if data.idempotency_key else None)
    create_audit_log(db, key.workspace_id, None, "ingestion.api_queued", "job", job.id)
    return {**serialize(job), "accepted": summary["accepted"], "rejected": summary["rejected"], "duplicates": summary["duplicates"], "message": "Accepted for asynchronous processing; final duplicate counts are in job status."}
