import json
import logging
import os
import time
from datetime import timedelta

from sqlalchemy import and_, delete, or_, select, update

from app.db import SessionLocal, utcnow
from app.models import (
    AuthSession,
    Job,
    Notification,
    RateBucket,
    Report,
    ResetToken,
    WorkerHeartbeat,
    Workspace,
)

logger = logging.getLogger("logsentinel.worker")
WORKER_ID = f"worker-{os.getpid()}"


def run_once() -> bool:
    with SessionLocal() as db:
        now = utcnow()
        heartbeat = db.get(WorkerHeartbeat, WORKER_ID)
        if heartbeat:
            heartbeat.last_seen = now
        else:
            db.add(WorkerHeartbeat(id=WORKER_ID, last_seen=now))
        db.commit()
        candidate = db.scalar(
            select(Job)
            .where(
                or_(
                    and_(Job.status == "queued", Job.available_at <= now),
                    and_(Job.status == "running", Job.lease_until < now),
                ),
                Job.attempts < 3,
            )
            .order_by(Job.created_at)
            .limit(1)
        )
        if not candidate:
            return False
        previous_attempts = candidate.attempts
        claimed = db.scalar(
            update(Job)
            .execution_options(synchronize_session=False)
            .where(
                Job.id == candidate.id,
                Job.attempts == previous_attempts,
                or_(Job.status == "queued", Job.lease_until < now),
            )
            .values(
                status="running",
                attempts=previous_attempts + 1,
                lease_until=now + timedelta(minutes=10),
            )
            .returning(Job.id)
        )
        db.commit()
        if not claimed:
            return False
        db.refresh(candidate)
        job_id, wid = candidate.id, candidate.workspace_id
        try:
            if candidate.kind == "ingestion":
                from app.ingestion import ingest_job

                ingest_job(db, candidate)
            elif candidate.kind == "detection":
                from app.detection import run_detection

                candidate.result = {"alerts_created": run_detection(db, wid)}
            elif candidate.kind == "report":
                from app.analytics import build_report

                build_report(db, candidate)
            elif candidate.kind == "retention":
                from app.admin import apply_retention

                apply_retention(db, candidate)
            else:
                raise ValueError("Unknown job type")
            candidate.status, candidate.progress, candidate.error = "completed", 100, None
            db.commit()
            if candidate.kind == "ingestion":
                from app.ingestion import STAGING

                (STAGING / candidate.payload["file"]).unlink(missing_ok=True)
        except Exception:
            db.rollback()
            failed = db.get(Job, job_id)
            if failed:
                failed.status = "failed" if failed.attempts >= 3 else "queued"
                failed.error = "Job processing failed. Check source configuration, data limits, and worker availability."
                failed.available_at = utcnow() + timedelta(seconds=2**failed.attempts)
                if failed.status == "failed":
                    if failed.kind == "report":
                        report = db.get(Report, failed.payload.get("report_id"))
                        if report:
                            report.status = "failed"
                    db.add(
                        Notification(
                            workspace_id=wid,
                            user_id=failed.actor_id,
                            title="A background job failed after three attempts",
                            link="/sources",
                        )
                    )
                db.commit()
            # Never log exception strings: parser and database exceptions can include log content.
            logger.error(json.dumps({"event": "job.failed", "job_id": job_id}))
        return True


def maintenance():
    with SessionLocal() as db:
        now = utcnow()
        stranded = list(
            db.scalars(
                select(Job).where(Job.status == "running", Job.lease_until < now, Job.attempts >= 3)
            )
        )
        for job in stranded:
            job.status = "failed"
            job.error = "Worker lease expired after the final attempt. Review and retry the job."
            db.add(
                Notification(
                    workspace_id=job.workspace_id,
                    user_id=job.actor_id,
                    title="A job exhausted its worker recovery attempts",
                    link="/sources",
                )
            )
        db.execute(delete(AuthSession).where(AuthSession.expires_at < now))
        db.execute(delete(ResetToken).where(ResetToken.expires_at < now))
        db.execute(delete(RateBucket).where(RateBucket.expires_at < now))
        db.execute(
            delete(WorkerHeartbeat).where(WorkerHeartbeat.last_seen < now - timedelta(days=1))
        )
        for workspace in db.scalars(select(Workspace)):
            # Periodic evaluation detects silent sources even when no new events arrive.
            detect_key = f"scheduled-detection:{now.strftime('%Y-%m-%dT%H:%M')}"
            if not db.scalar(
                select(Job.id).where(
                    Job.workspace_id == workspace.id, Job.idempotency_key == detect_key
                )
            ):
                db.add(
                    Job(
                        workspace_id=workspace.id,
                        kind="detection",
                        payload={},
                        idempotency_key=detect_key,
                    )
                )
            if workspace.settings.get("auto_retention", False):
                key = f"retention:{now.date().isoformat()}"
                existing = db.scalar(
                    select(Job.id).where(
                        Job.workspace_id == workspace.id, Job.idempotency_key == key
                    )
                )
                if not existing:
                    db.add(
                        Job(
                            workspace_id=workspace.id,
                            kind="retention",
                            payload={},
                            idempotency_key=key,
                        )
                    )
        db.commit()


def main():
    logging.basicConfig(level=logging.INFO)
    last_maintenance = 0.0
    while True:
        try:
            if time.monotonic() - last_maintenance > 60:
                maintenance()
                last_maintenance = time.monotonic()
            if not run_once():
                time.sleep(1)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.error(json.dumps({"event": "worker.cycle_failed"}))
            time.sleep(5)


if __name__ == "__main__":
    main()
