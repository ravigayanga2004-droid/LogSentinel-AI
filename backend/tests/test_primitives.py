import json
from datetime import UTC

import pytest

from app.parsers import ParseError, csv_preview, parse_line, parse_timestamp
from app.privacy import redact_event, redact_sensitive_fields, redact_text, safe_cell, safe_path
from app.security import entity_hash, hash_password, require_permission, verify_password
from app.statistics import anomaly, baseline, percentile


def test_password_hashing():
    hashed = hash_password("valid-long-passphrase")
    assert hashed.startswith("$argon2id$")
    assert verify_password("valid-long-passphrase", hashed)
    assert not verify_password("incorrect", hashed)


@pytest.mark.parametrize("password", ["short", "a" * 129])
def test_password_limits(password):
    with pytest.raises(ValueError):
        hash_password(password)


def test_entity_hash():
    assert entity_hash("192.0.2.1") == entity_hash("192.0.2.1")
    assert entity_hash("192.0.2.1") != entity_hash("192.0.2.2")
    assert len(entity_hash("user")) == 64


@pytest.mark.parametrize("text,secret", [('password="with spaces"', "with spaces"), ("Authorization: Bearer abc123", "abc123"), ("api_key=super-secret", "super-secret"), ('{"token":"abcXYZ"}', "abcXYZ")])
def test_redaction(text, secret):
    assert secret not in redact_text(text)


def test_nested_redaction():
    assert redact_sensitive_fields({"nested": {"password": "secret"}, "items": ["email@example.org 192.0.2.1"]}) == {"nested": {"password": "[REDACTED]"}, "items": ["[EMAIL] [IP]"]}


def test_event_privacy():
    value = redact_event(parse_line(json.dumps({"message": "user alice from 192.0.2.3", "username": "alice", "ip": "192.0.2.3", "path": "/admin?token=abc"})))
    assert "alice" not in str(value)
    assert "192.0.2.3" not in str(value)
    assert value["url_path"] == "/admin"
    assert value["username_hash"]


@pytest.mark.parametrize("value", ["=HYPERLINK('evil')", "+cmd", "@SUM(1)", " -123"])
def test_export_formula_escape(value):
    assert safe_cell(value).startswith("'")


def test_path_removes_query():
    assert safe_path("/path?password=123#secret") == "/path"


@pytest.mark.parametrize("timestamp", ["2026-01-01T12:00:00Z", "2026-01-01T14:00:00+02:00", 1767268800, 1767268800000])
def test_timestamp_utc(timestamp):
    assert parse_timestamp(timestamp).tzinfo == UTC
    assert parse_timestamp(timestamp).hour == 12


def test_auth_parser():
    event = parse_line("Oct 19 08:01:02 host sshd[123]: Failed password for invalid user alice from 192.0.2.1 port 22 ssh2")
    assert event["event_type"] == "login_failed"
    assert event["source_ip"] == "192.0.2.1"
    assert event["username"] == "alice"


def test_access_parser():
    event = parse_line('192.0.2.1 - - [19/Oct/2026:08:01:02 +0000] "GET /admin?token=abc HTTP/1.1" 403 12')
    assert event["status_code"] == 403
    assert event["category"] == "web"


def test_key_value_parser():
    assert parse_line('message="hello world" level=error', "key_value")["severity"] == "high"


@pytest.mark.parametrize("line,parser", [("{broken", "json"), ("[]", "json"), ("hello", "linux_auth"), ("", "auto"), ("a" * 65537, "auto"), ('{"message":"x","timestamp":"bad"}', "json")])
def test_safe_parse_errors(line, parser):
    with pytest.raises(ParseError):
        parse_line(line, parser)


def test_csv_mapping():
    assert csv_preview("when,text\n2026-01-01,hello", {"timestamp": "when", "message": "text"})[0]["message"] == "hello"
    with pytest.raises(ParseError):
        csv_preview("a,b\n1,2", {})


def test_statistics_require_history():
    assert not anomaly(100, baseline([1, 2]))["triggered"]
    stats = baseline([2.0] * 20)
    assert stats["trusted"]
    assert stats["mad"] == 0
    assert anomaly(100, stats)["triggered"]
    assert not anomaly(2, stats)["triggered"]
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def test_role_restrictions():
    require_permission("analyst", "investigate")
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        require_permission("viewer", "admin")
