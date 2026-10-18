import json
from datetime import timedelta

import pytest
from app.auth import create_reset
from app.db import utcnow
from app.models import Member, User
from sqlalchemy import select


def batch(client, source, records, key=None):
    secret = client.post(f"/api/sources/{source['id']}/keys", json={"name": "Test key"}).json()[
        "key"
    ]
    return client.post(
        "/api/ingest",
        headers={"x-api-key": secret},
        json={"events": records, "idempotency_key": key},
    )


def test_setup_one_time(client):
    assert not client.get("/api/auth/status").json()["setup_required"]
    assert (
        client.post(
            "/api/auth/setup",
            json={"name": "Other", "email": "other@example.com", "password": "Other-Password!"},
        ).status_code
        == 409
    )


def test_session_csrf_and_logout(client):
    assert client.get("/api/auth/me").status_code == 200
    csrf = client.headers.pop("x-csrf-token")
    assert client.post("/api/sources", json={"name": "denied"}).status_code == 403
    client.headers["x-csrf-token"] = csrf
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/events").status_code == 401


def test_bad_origin(client):
    assert (
        client.post(
            "/api/sources", headers={"origin": "https://untrusted.invalid"}, json={"name": "denied"}
        ).status_code
        == 403
    )


def test_validation_does_not_echo_secrets(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "not-email-secret", "password": "secret-password", "token": "private-token"},
    )
    assert response.status_code == 422
    assert "private-token" not in response.text
    assert "secret-password" not in response.text


def test_ingest_detect_investigate_export(system, source):
    client, factory, worker = system
    now = utcnow()
    records = [
        {
            "timestamp": (now - timedelta(seconds=i)).isoformat(),
            "message": "Failed login password=top-secret",
            "event_type": "login_failed",
            "category": "authentication",
            "ip": "192.0.2.1",
            "username": "alice",
        }
        for i in range(8)
    ]
    response = batch(client, source, records, "first-import")
    assert response.status_code == 202, response.text
    assert worker.run_once()
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "completed", job
    events = client.get("/api/events").json()
    assert events["total"] == 8
    assert "top-secret" not in json.dumps(events)
    assert "192.0.2.1" not in json.dumps(events)
    alerts = client.get("/api/alerts").json()["items"]
    alert = next(row for row in alerts if row["title"] == "Failed login burst")
    detail = client.get(f"/api/alerts/{alert['id']}").json()
    assert detail["explanation"]["observed"] == 8
    assert len(detail["events"]) == 8
    assert (
        client.post(
            f"/api/alerts/{alert['id']}/notes", json={"body": "Check maintenance token=private"}
        ).status_code
        == 201
    )
    assert (
        client.patch(f"/api/alerts/{alert['id']}", json={"status": "RESOLVED"}).status_code == 422
    )
    assert (
        client.patch(
            f"/api/alerts/{alert['id']}",
            json={"status": "RESOLVED", "resolution_reason": "Approved test activity"},
        ).status_code
        == 200
    )
    report = client.post("/api/reports", json={"title": "Test", "format": "json"}).json()
    assert worker.run_once()
    downloaded = client.get(f"/api/reports/{report['id']}/download")
    assert downloaded.status_code == 200, downloaded.text
    assert "top-secret" not in downloaded.text
    assert len(downloaded.json()["events"]) == 8
    assert client.get("/api/analytics").json()["total_events"] == 8


def test_idempotency_and_dedup(system, source):
    client, _, worker = system
    records = [{"timestamp": utcnow().isoformat(), "message": "same event"}] * 3
    one = batch(client, source, records, "same-key")
    two = batch(client, source, records, "same-key")
    assert one.json()["id"] == two.json()["id"]
    worker.run_once()
    assert client.get("/api/events").json()["total"] == 1
    assert client.get(f"/api/jobs/{one.json()['id']}").json()["result"]["duplicates"] == 2
    assert client.get("/api/events").json()["items"][0]["duplicates"] == 2


def test_csv_requires_valid_mapping(system, source):
    client, _, worker = system
    path = f"/api/sources/{source['id']}/upload"
    data = "when,text\n2026-10-19T00:00:00Z,sample\nbad,invalid\n"
    assert client.post(path, files={"file": ("test.csv", data, "text/csv")}).status_code == 422
    mapping = json.dumps({"timestamp": "when", "message": "text"})
    assert (
        client.post(
            path, files={"file": ("test.csv", data, "text/csv")}, data={"mapping": mapping}
        ).status_code
        == 422
    )
    assert client.get("/api/events").json()["total"] == 0
    response = client.post(
        path,
        files={"file": ("test.csv", data, "text/csv")},
        data={"mapping": mapping, "allow_partial": "true"},
    )
    assert response.status_code == 202, response.text
    worker.run_once()
    assert client.get("/api/events").json()["total"] == 2


def test_malformed_partial_file(system, source):
    client, _, worker = system
    response = client.post(
        f"/api/sources/{source['id']}/upload",
        files={"file": ("events.jsonl", '{broken\n{"message":"valid"}', "text/plain")},
        data={"allow_partial": "true"},
    )
    assert response.status_code == 202
    worker.run_once()
    events = client.get("/api/events").json()
    assert events["total"] == 2
    assert any(event["parse_status"] == "failed" for event in events["items"])


@pytest.mark.parametrize("filename", ["payload.exe", "archive.zip", "script.html"])
def test_disallowed_uploads(client, source, filename):
    assert (
        client.post(
            f"/api/sources/{source['id']}/upload", files={"file": (filename, "test")}
        ).status_code
        == 415
    )


def test_workspace_isolation(client, source):
    other = client.post("/api/workspaces", json={"name": "Other"}).json()
    client.headers["x-workspace-id"] = other["id"]
    assert client.get(f"/api/sources/{source['id']}").status_code == 404
    assert client.get("/api/events").json()["total"] == 0
    client.headers["x-workspace-id"] = "does-not-exist"
    assert client.get("/api/events").status_code == 403


@pytest.mark.parametrize("role", ["viewer", "analyst", "source_admin"])
def test_roles_enforced(system, source, role):
    client, factory, _ = system
    with factory() as db:
        member = db.scalar(select(Member))
        member.role = role
        db.commit()
    assert client.get("/api/events").status_code == 200
    assert client.get("/api/settings").status_code == 403
    assert (
        client.post(
            "/api/members",
            json={"email": "new@example.com", "name": "New", "password": "New-Password!"},
        ).status_code
        == 403
    )
    assert client.post("/api/sources", json={"name": "Source"}).status_code == (
        201 if role == "source_admin" else 403
    )
    assert client.post("/api/reports", json={}).status_code == (202 if role == "analyst" else 403)
    assert client.post("/api/detection/run").status_code == (202 if role == "analyst" else 403)


def test_last_administrator_protected(client):
    user = client.get("/api/auth/me").json()
    assert client.patch(f"/api/members/{user['id']}", json={"role": "viewer"}).status_code == 409


def test_reset_one_time_and_invalidates_sessions(system):
    client, factory, _ = system
    with factory() as db:
        user = db.scalar(select(User))
        raw = create_reset(db, user)
        db.commit()
    response = client.post(
        "/api/auth/reset-password", json={"token": raw, "password": "Changed-Password!"}
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/reset-password", json={"token": raw, "password": "Changed-Password!"}
        ).status_code
        == 400
    )


def test_api_key_revocation(client, source):
    key = client.post(f"/api/sources/{source['id']}/keys", json={"name": "Agent"}).json()
    assert client.delete(f"/api/keys/{key['id']}").status_code == 200
    assert (
        client.post(
            "/api/ingest", headers={"x-api-key": key["key"]}, json={"events": [{"message": "test"}]}
        ).status_code
        == 401
    )
    assert key["key"] not in client.get("/api/keys").text


def test_rule_validation_and_version(client):
    bad = client.post("/api/rules", json={"name": "Bad", "config": {"paths": [""]}})
    assert bad.status_code == 422
    rule = client.post("/api/rules", json={"name": "Custom burst", "kind": "failed_login"}).json()
    assert (
        client.put(f"/api/rules/{rule['id']}", json={"name": "Updated", "threshold": 8}).json()[
            "version"
        ]
        == 2
    )
    assert client.post(f"/api/rules/{rule['id']}/test").json()["test_only"]


def test_source_silence_and_duplicate_alerts(system, source):
    client, factory, worker = system
    from app.models import Source

    with factory() as db:
        src = db.get(Source, source["id"])
        src.last_event_at = utcnow() - timedelta(hours=3)
        db.commit()
    client.post("/api/detection/run")
    worker.run_once()
    before = client.get("/api/alerts").json()["total"]
    assert before >= 1
    client.post("/api/detection/run")
    worker.run_once()
    assert client.get("/api/alerts").json()["total"] == before


def test_retention_preview_and_execution(system, source):
    client, factory, worker = system
    batch(
        client,
        source,
        [{"timestamp": (utcnow() - timedelta(days=40)).isoformat(), "message": "expired event"}],
    )
    worker.run_once()
    assert client.get("/api/retention/preview").json()["counts"]["events"] == 1
    client.post("/api/retention/run")
    worker.run_once()
    assert client.get("/api/events").json()["total"] == 0
    assert any(
        row["action"] == "retention.completed" for row in client.get("/api/audit").json()["items"]
    )


def test_search_and_headers(client):
    response = client.get("/api/events", params={"q": "' OR 1=1 --"})
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/api/events?page_size=10000").status_code == 422
