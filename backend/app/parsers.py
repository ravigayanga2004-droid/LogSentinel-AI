"""Versioned, bounded parsers. Input is data and is never executed."""

import csv
import io
import json
import re
import shlex
from datetime import UTC, datetime
from typing import Any

from app.db import utcnow

PARSERS = ("auto", "json", "linux_auth", "nginx", "apache", "key_value", "generic", "windows")
ACCESS = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "([A-Z]+) (\S+)(?: [^"\n]*)?" (\d{3})(?: .*)?$')
AUTH = re.compile(
    r"(?P<ts>[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}|\d{4}-\d\d-\d\dT\S+)\s+(?P<host>\S+)\s+(?P<process>[\w/-]+)(?:\[\d+\])?:\s*(?P<message>.*)"
)
LOGIN = re.compile(
    r"(?P<action>Failed|Accepted) (?:password|publickey) for (?:invalid user )?(?P<user>\S+) from (?P<ip>\S+)",
    re.I,
)


class ParseError(ValueError):
    pass


def parse_timestamp(value: Any) -> datetime:
    if value is None or value == "":
        return utcnow()
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        result = datetime.fromtimestamp(value / 1000 if value > 1e11 else value, UTC)
    else:
        text = str(value).strip()
        try:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                result = datetime.strptime(text, "%d/%b/%Y:%H:%M:%S %z")
            except ValueError:
                result = datetime.strptime(f"{utcnow().year} {text}", "%Y %b %d %H:%M:%S")
                # Syslog omits year: late-December events arriving in January belong to last year.
                if (result.replace(tzinfo=UTC) - utcnow()).days > 1:
                    result = result.replace(year=result.year - 1)
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def severity(value: Any) -> str:
    text = str(value).lower()
    return {
        "fatal": "critical",
        "emergency": "critical",
        "error": "high",
        "err": "high",
        "warning": "medium",
        "warn": "medium",
        "debug": "low",
        "information": "info",
        "informational": "info",
    }.get(text, text if text in {"critical", "high", "medium", "low", "info"} else "info")


def normalize(obj: dict, parser: str) -> dict:
    if not isinstance(obj, dict):
        raise ParseError("Record must be an object")
    message = obj.get("message", obj.get("msg", obj.get("Message", "")))
    if not isinstance(message, str) or not message.strip():
        raise ParseError("A nonempty message field is required")
    code = obj.get("status_code", obj.get("statusCode", obj.get("status")))
    if code is not None:
        code = int(code)
        if not 100 <= code <= 599:
            raise ParseError("HTTP status must be between 100 and 599")
    category = str(obj.get("category", "web" if code else "application"))[:40]
    event_type = str(
        obj.get("event_type", obj.get("eventType", "http_request" if code else "log"))
    )[:60]
    return {
        "timestamp": parse_timestamp(obj.get("timestamp", obj.get("time", obj.get("TimeCreated")))),
        "message": message[:16000],
        "severity": severity(obj.get("severity", obj.get("level", "info"))),
        "event_type": event_type,
        "category": category,
        "status_code": code,
        "username": str(obj.get("username", obj.get("user", "")))[:200],
        "source_ip": str(obj.get("source_ip", obj.get("ip", obj.get("remote_addr", ""))))[:100],
        "source_host": str(obj.get("host", obj.get("source_host", "")))[:100],
        "service": str(obj.get("service", obj.get("application", "")))[:100],
        "url_path": str(obj.get("url_path", obj.get("path", "")))[:2000],
        "http_method": str(obj.get("method", ""))[:16],
        "outcome": str(obj.get("outcome", "failure" if code and code >= 400 else "unknown"))[:30],
        "parser_name": parser,
        "details": {
            "metadata": obj.get("metadata", {}),
            "request_id": str(obj.get("request_id", ""))[:100],
            "process": str(obj.get("process", ""))[:100],
        },
    }


def parse_line(line: str, parser: str = "auto") -> dict:
    if parser not in PARSERS:
        raise ParseError("Unknown parser")
    if len(line.encode("utf-8")) > 65536:
        raise ParseError("Line exceeds 64 KiB")
    line = line.strip()
    if not line:
        raise ParseError("Empty record")
    try:
        if parser in {"json", "windows"} or (parser == "auto" and line.startswith(("{", "["))):
            return normalize(json.loads(line), "windows" if parser == "windows" else "json")
        access = ACCESS.match(line)
        if access and parser in {"auto", "nginx", "apache"}:
            ip, timestamp, method, path, code = access.groups()
            return normalize(
                {
                    "message": f"{method} {path.split('?')[0]} returned {code}",
                    "timestamp": timestamp,
                    "ip": ip,
                    "method": method,
                    "path": path,
                    "status": code,
                    "severity": "error"
                    if int(code) >= 500
                    else "warning"
                    if int(code) >= 400
                    else "info",
                },
                "apache" if parser == "apache" else "nginx",
            )
        auth = AUTH.match(line)
        if auth and parser in {"auto", "linux_auth"}:
            fields = auth.groupdict()
            login = LOGIN.search(fields["message"])
            obj = {
                "message": fields["message"],
                "timestamp": fields["ts"],
                "host": fields["host"],
                "service": fields["process"],
                "category": "authentication",
                "event_type": "auth_event",
            }
            if login:
                failed = login["action"].lower() == "failed"
                obj.update(
                    username=login["user"],
                    ip=login["ip"],
                    event_type="login_failed" if failed else "login_success",
                    severity="warning" if failed else "info",
                    outcome="failure" if failed else "success",
                )
            return normalize(obj, "linux_auth")
        if parser == "key_value" or (parser == "auto" and re.search(r"\b(?:message|msg)=", line)):
            fields = dict(part.split("=", 1) for part in shlex.split(line) if "=" in part)
            return normalize(fields, "key_value")
        if parser not in {"auto", "generic"}:
            raise ParseError("Record does not match the selected parser")
        level = re.search(r"\b(CRITICAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\b", line, re.I)
        timestamp = re.match(r"^(\d{4}-\d\d-\d\d[T ][\d:.]+(?:Z|[+-]\d\d:\d\d)?)", line)
        return normalize(
            {
                "message": line,
                "severity": level[1] if level else "info",
                "timestamp": timestamp[1] if timestamp else None,
            },
            "generic",
        )
    except (ValueError, TypeError, OverflowError, KeyError, RecursionError) as exc:
        if isinstance(exc, ParseError):
            raise
        raise ParseError("Record contains invalid fields, JSON, or timestamp") from None


def csv_preview(text: str, mapping: dict[str, str]) -> list[dict]:
    if not mapping.get("timestamp") or not mapping.get("message"):
        raise ParseError("Map timestamp and message columns before importing CSV")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or any(column not in reader.fieldnames for column in mapping.values()):
        raise ParseError("Mapped columns were not found in the CSV header")
    return [{field: row.get(column, "") for field, column in mapping.items()} for row in reader]
