"""Explicit synthetic development fixtures; never runs on application startup."""

import random
from datetime import timedelta

from sqlalchemy import select

from app.common import create_audit_log
from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.detection import seed_rules
from app.ingestion import STAGING, enqueue_ingestion, ingest_job, stage_records
from app.models import Alert, Member, Note, Source, User, Workspace
from app.security import hash_password

DEMO_PASSWORD = "Sentinel-Demo-2026!"  # noqa: S105 -- explicit development fixture


def seed():
    if get_settings().environment == "production":
        raise ValueError("Demo data cannot be installed in production")
    rng = random.Random(42)
    with SessionLocal() as db:
        # Repair the initial development-only fixture domain without changing its data.
        for name in ("admin", "analyst", "viewer", "source"):
            legacy = db.scalar(select(User).where(User.email == f"{name}@logsentinel.local"))
            if legacy:
                legacy.email = f"{name}@logsentinel.example.com"
        db.commit()
        if db.scalar(select(User).where(User.email == "admin@logsentinel.example.com")):
            return "Demo already exists; no existing data changed."
        workspace = Workspace(name="Acme Security · Demo", settings={"privacy_mode": True})
        db.add(workspace)
        db.flush()
        users = []
        for name, role, email in [
            ("Alex Morgan", "administrator", "admin"),
            ("Jordan Lee", "analyst", "analyst"),
            ("Sam Rivera", "viewer", "viewer"),
            ("Casey Chen", "source_admin", "source"),
        ]:
            user = User(
                name=name,
                email=f"{email}@logsentinel.example.com",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            db.flush()
            db.add(Member(workspace_id=workspace.id, user_id=user.id, role=role))
            users.append(user)
        seed_rules(db, workspace.id, users[0].id)
        now = utcnow()
        sources = [
            Source(
                workspace_id=workspace.id,
                name="Production · SSH",
                type="linux_auth",
                parser="auto",
                host="auth-prod-01",
                description="Synthetic Linux authentication events",
            ),
            Source(
                workspace_id=workspace.id,
                name="Edge · Nginx",
                type="web",
                parser="auto",
                host="edge-prod-02",
                description="Synthetic web access events",
            ),
            Source(
                workspace_id=workspace.id,
                name="Payments · API",
                type="application",
                parser="json",
                host="api-prod-01",
                description="Synthetic application JSON logs",
            ),
            Source(
                workspace_id=workspace.id,
                name="Staging · Database",
                type="database",
                parser="json",
                host="db-stage-01",
                description="Synthetic source silence example",
                last_event_at=now - timedelta(hours=4),
                silence_minutes=60,
            ),
        ]
        db.add_all(sources)
        db.flush()
        for source_index, source in enumerate(sources[:3]):
            records: list[dict] = []
            for minute in range(1, 1440):
                count = rng.randint(1, 4)
                for step in range(count):
                    stamp = now - timedelta(minutes=minute, seconds=step * 10)
                    if source_index == 0:
                        failed = rng.random() < 0.04
                        records.append(
                            {
                                "timestamp": stamp.isoformat(),
                                "message": "Synthetic SSH authentication sample",
                                "event_type": "login_failed" if failed else "login_success",
                                "category": "authentication",
                                "username": f"demo-user-{minute % 5}",
                                "ip": f"192.0.2.{minute % 12 + 1}",
                                "service": "sshd",
                                "severity": "medium" if failed else "info",
                                "outcome": "failure" if failed else "success",
                            }
                        )
                    else:
                        code = rng.choices([200, 201, 304, 404, 500], [65, 15, 15, 4, 1])[0]
                        records.append(
                            {
                                "timestamp": stamp.isoformat(),
                                "message": "Synthetic request completed",
                                "status_code": code,
                                "path": rng.choice(
                                    ["/api/health", "/api/orders", "/dashboard", "/api/search"]
                                ),
                                "ip": f"198.51.100.{minute % 30 + 1}",
                                "service": "nginx" if source_index == 1 else "payments-api",
                                "severity": "high" if code >= 500 else "info",
                                "category": "web",
                            }
                        )
            if source_index == 0:
                for number in range(24):
                    records.append(
                        {
                            "timestamp": (now - timedelta(seconds=120 - number * 3)).isoformat(),
                            "message": "Synthetic failed password for demo-intruder from 203.0.113.42 password=must-redact",
                            "event_type": "login_failed",
                            "category": "authentication",
                            "username": "demo-intruder",
                            "ip": "203.0.113.42",
                            "service": "sshd",
                            "severity": "medium",
                            "outcome": "failure",
                        }
                    )
                records.append(
                    {
                        "timestamp": (now - timedelta(seconds=10)).isoformat(),
                        "message": "Synthetic successful authentication after failures",
                        "event_type": "login_success",
                        "category": "authentication",
                        "username": "demo-intruder",
                        "ip": "203.0.113.42",
                        "service": "sshd",
                        "outcome": "success",
                    }
                )
            if source_index == 1:
                for number in range(35):
                    records.append(
                        {
                            "timestamp": (now - timedelta(seconds=number + 5)).isoformat(),
                            "message": "Synthetic upstream timeout",
                            "status_code": 503,
                            "path": "/api/payments",
                            "ip": "203.0.113.20",
                            "severity": "high",
                            "service": "nginx",
                        }
                    )
            filename, summary = stage_records(iter(records), source, workspace.settings)
            job = enqueue_ingestion(db, source, users[0].id, filename, summary)
            ingest_job(db, job)
            job.status, job.progress = "completed", 100
            db.commit()
            (STAGING / filename).unlink(missing_ok=True)
        filename, summary = stage_records(
            iter(["{malformed-json"] * 4), sources[2], workspace.settings
        )
        job = enqueue_ingestion(db, sources[2], users[0].id, filename, summary)
        ingest_job(db, job)
        job.status, job.progress = "completed", 100
        alert = db.scalar(select(Alert).where(Alert.workspace_id == workspace.id))
        if alert:
            alert.assignee_id = users[1].id
            db.add(
                Note(
                    workspace_id=workspace.id,
                    alert_id=alert.id,
                    author_id=users[1].id,
                    body="Synthetic investigation: compare this sequence with approved maintenance and contact the system owner.",
                    evidence=[],
                )
            )
        create_audit_log(db, workspace.id, users[0].id, "demo.seeded", "workspace", workspace.id)
        db.commit()
        (STAGING / filename).unlink(missing_ok=True)
    return "Synthetic demo installed. Development password: Sentinel-Demo-2026! Change before production."
