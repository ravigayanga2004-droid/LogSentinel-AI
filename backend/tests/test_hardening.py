import json
import time
from datetime import timedelta

import pytest
from app.db import utcnow
from app.models import Baseline, Event, Job, Source
from sqlalchemy import func, select


def test_shared_login_lockout(client):
    for _ in range(8):
        assert (
            client.post(
                "/api/auth/login", json={"email": "admin@example.com", "password": "wrong-password"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "Admin-Test-Password!"},
        ).status_code
        == 429
    )


def test_request_and_file_size_limits(client, source):
    assert (
        client.post(
            "/api/auth/login",
            content="{}",
            headers={"content-length": "999999999", "content-type": "application/json"},
        ).status_code
        == 413
    )
    response = client.post(
        f"/api/sources/{source['id']}/upload",
        files={"file": ("large.log", b"x" * (10 * 1024 * 1024 + 1))},
    )
    assert response.status_code == 413


def test_file_preview_is_redacted_and_does_not_import(client, source):
    response = client.post(
        f"/api/sources/{source['id']}/preview",
        files={"file": ("test.jsonl", '{"message":"password=sample-private","ip":"192.0.2.33"}')},
    )
    assert response.status_code == 200
    assert response.json()["test_only"]
    assert "sample-private" not in response.text
    assert "192.0.2.33" not in response.text
    assert client.get("/api/events").json()["total"] == 0


@pytest.mark.parametrize(
    "filters",
    [
        {"q": []},
        {"hours": {}},
        {"source_id": {"$ne": ""}},
        {"unknown": "field"},
        {"hours": -1},
        {"start": "not-a-date"},
    ],
)
def test_report_filter_validation(client, filters):
    response = client.post("/api/reports", json={"filters": filters})
    assert response.status_code == 422


def test_export_disabled_by_policy(client):
    policy = client.get("/api/settings").json()["policy"]
    policy["exports_enabled"] = False
    assert client.put("/api/settings", json=policy).status_code == 200
    assert client.post("/api/reports", json={}).status_code == 403


def test_worker_recovers_expired_lease_once(system, source):
    client, factory, worker = system
    with factory() as db:
        job = Job(
            workspace_id=source["workspace_id"],
            kind="detection",
            status="running",
            lease_until=utcnow() - timedelta(minutes=1),
            attempts=1,
            payload={},
        )
        db.add(job)
        db.commit()
        job_id = job.id
    assert worker.run_once()
    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "completed"
    assert status["attempts"] == 2
    assert not worker.run_once()
    with factory() as db:
        db.add(
            Job(
                workspace_id=source["workspace_id"],
                kind="detection",
                status="running",
                lease_until=utcnow() + timedelta(minutes=10),
                attempts=1,
                payload={},
            )
        )
        db.commit()
    assert not worker.run_once(), "A worker must not steal an active lease, including a demo import"


def test_ingestion_retry_does_not_increment_duplicates(system, source):
    client, factory, worker = system
    from app.ingestion import enqueue_ingestion, ingest_job, stage_records

    with factory() as db:
        src = db.get(Source, source["id"])
        filename, summary = stage_records(
            iter(
                [{"timestamp": utcnow().isoformat(), "message": f"record {i}"} for i in range(300)]
            ),
            src,
            {},
        )
        job = enqueue_ingestion(db, src, None, filename, summary)
        db.commit()
        ingest_job(db, job)
        db.commit()
        ingest_job(db, job)
        db.commit()
        assert db.scalar(select(func.count()).select_from(Event)) == 300
        assert db.scalar(select(func.sum(Event.duplicates))) == 0


def test_baseline_reset_excludes_old_history(system, source):
    client, factory, worker = system
    from app.detection import update_baselines
    from app.ingestion import enqueue_ingestion, ingest_job, stage_records

    with factory() as db:
        src = db.get(Source, source["id"])
        records = [
            {
                "timestamp": (utcnow() - timedelta(minutes=10 + i * 5)).isoformat(),
                "message": f"history {i}",
            }
            for i in range(30)
        ]
        filename, summary = stage_records(iter(records), src, {})
        job = enqueue_ingestion(db, src, None, filename, summary)
        ingest_job(db, job)
        db.commit()
        row = db.scalar(select(Baseline))
        assert row.stats["trusted"]
        row_id = row.id
    assert client.post(f"/api/baselines/{row_id}/reset").status_code == 200
    with factory() as db:
        update_baselines(db, source["workspace_id"])
        db.commit()
        assert db.get(Baseline, row_id).stats["samples"] == 0


def test_parser_failure_count_preserves_repeated_invalid_records(system, source):
    client, factory, worker = system
    result = client.post(
        f"/api/sources/{source['id']}/upload",
        files={"file": ("bad.jsonl", "{invalid\n" * 4)},
        data={"allow_partial": "true"},
    )
    assert result.status_code == 202
    worker.run_once()
    alerts = client.get("/api/alerts").json()["items"]
    assert any(
        alert["title"] == "Repeated parser failures" and alert["explanation"]["observed"] == 4
        for alert in alerts
    )


def test_large_batched_import_is_paginated_and_bounded(system, source):
    client, factory, worker = system
    count = 5000
    records = "\n".join(
        json.dumps({"timestamp": utcnow().isoformat(), "message": f"load fixture {index}"})
        for index in range(count)
    )
    started = time.monotonic()
    response = client.post(
        f"/api/sources/{source['id']}/upload", files={"file": ("load.jsonl", records)}
    )
    assert response.status_code == 202
    worker.run_once()
    elapsed = time.monotonic() - started
    status = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert status["status"] == "completed", status
    result = client.get("/api/events?page_size=100&page_number=50").json()
    assert result["total"] == count
    assert len(result["items"]) == 100
    assert elapsed < 60


def test_cross_workspace_report_and_rule_access(client):
    report = client.post("/api/reports", json={}).json()
    rule = client.get("/api/rules").json()["items"][0]
    other = client.post("/api/workspaces", json={"name": "Isolated"}).json()
    client.headers["x-workspace-id"] = other["id"]
    assert client.get(f"/api/reports/{report['id']}/download").status_code == 404
    assert client.post(f"/api/rules/{rule['id']}/test").status_code == 404
